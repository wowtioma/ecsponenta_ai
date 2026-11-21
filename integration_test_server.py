import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from zipfile import ZipFile

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from llm import Journal, KnowledgeBase, LLMClient, answer_fact, build_timing, build_usage, extract
from llm import config as llm_config
from llm import detect_unsupported, save_session
from llm.answer import explain_placement, explain_rules
from llm.client import GroqRateLimit
from llm.dialogue_wording import compose_project_reply, wants_detailed_explanation
from llm.extract import _norm_checks
from llm import prompts

prompts.SYSTEM_FACT += (
    "\nИсточник интерфейс показывает отдельно из метаданных поиска. "
    "В тексте ответа не указывай файл, номер раздела или строку «Источник»."
)

from b_adapter import session_from_extraction
from rules import PROTOCOLS, Session, apply_answer, evaluate, protocol_name, record_unresolved_answer
from project_edits import (
    continue_project_edit, describe_changes, edit_project, is_recipient_reply, project_context,
)
from project_dialogue import (
    ACKNOWLEDGEMENT, ADD_FLOW_REQUEST, explain_current_project, is_project_question, merge_project_extraction,
    resolve_file_directions,
)

journal = Journal()
sessions = {}
last_project_messages = {}
shown_questions = {}
pending_edits = {}
pending_antivirus = {}
turns = {}
client: LLMClient | None = None
MODEL_WORDING_ENABLED = os.environ.get("SYNONYX_LLM_WORDING", "1").strip().lower() not in {"0", "false"}

FACT_QUESTION = re.compile(
    r'^\s*[«"]?\s*(?:сколько\s+правил\b|'
    r"(?:зачем|почему)\b[^.!?\n]{0,60}\b(?:межсетевой\s+экран|мэ)\b)",
    re.I,
)


class FormAnswerError(ValueError):
    pass


USER_COUNT_WORDS = {
    "ноль": 0, "нуль": 0, "один": 1, "одна": 1, "два": 2, "две": 2,
    "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
    "девять": 9, "десять": 10,
}


def manual_user_count(answer):
    match = re.fullmatch(
        r"(?P<number>[0-9]{1,9}|[а-яё]+)(?:\s+(?:файлов\w*\s+)?"
        r"(?:пользовател\w*|человек\w*|людей|сотрудни\w*))?",
        answer,
    )
    if not match:
        return None
    number = match["number"]
    return int(number) if number.isascii() and number.isdecimal() else USER_COUNT_WORDS.get(number)


def is_form_reply(questions, message):
    return any(message.strip().startswith(question["text"] + " ") for question in questions)


def apply_form(session, questions, message):
    explicit = is_form_reply(questions, message)
    if len(questions) == 1 and not explicit:
        if "\n" in message or len(message) > 180:
            return None
        answered = [(questions[0], message.strip())]
    else:
        by_text = {question["text"]: question for question in questions}
        labels = "|".join(re.escape(label) for label in sorted(by_text, key=len, reverse=True))
        body = message.strip()
        matches = list(re.finditer(rf"^(?P<question>{labels}) ", body, flags=re.M))
        if not matches or matches[0].start() != 0:
            return None
        answered = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            answer = body[match.end():end].strip()
            if not answer:
                return None
            answered.append((by_text[match["question"]], answer))

    return apply_question_answers(session, answered, explicit=explicit)


def apply_question_answers(session, answered, *, explicit):
    for question, answer in sorted(answered, key=lambda item: item[0]["id"].endswith(".access_groups")):
        key = question["id"]
        normalized = answer.strip().casefold().rstrip(".!")
        if normalized in ("не знаю", "я не знаю", "неизвестно", "null"):
            session = record_unresolved_answer(session, key)
        elif key == "manual_users_count":
            count = manual_user_count(normalized)
            if count is None:
                if explicit:
                    raise FormAnswerError("Укажите число людей, например «1» или «один сотрудник».")
                return None
            session = apply_answer(session, key, count)
        elif key == "networks" and len(session.networks) == 1:
            known = session.networks[0]
            if normalized in (known.id.casefold(), known.name.casefold()):
                raise FormAnswerError("Укажите вторую сеть, которая будет обмениваться файлами или данными с уже указанной.")
            kind = {"closed": "open", "open": "closed"}.get(known.kind)
            name = answer.strip()
            if kind and normalized in ("открытая и закрытая", "закрытая и открытая"):
                name = {"open": "Открытая сеть", "closed": "Закрытая сеть"}[kind]
            reserved = {known.id}
            network_id = next(candidate for candidate in (kind, "other-network", "network-2")
                              if candidate and candidate not in reserved)
            session = apply_answer(session, key, [
                known.model_dump(), {"id": network_id, "name": name, "kind": kind},
            ])
        elif key.endswith("_network_id"):
            network = next((n for n in session.networks if normalized in (n.id.casefold(), n.name.casefold())), None)
            if network is None:
                session = record_unresolved_answer(session, key, answer)
            elif network.name not in question["options"]:
                raise FormAnswerError("Для этого потока выберите сеть на другой стороне обмена.")
            else:
                session = apply_answer(session, key, network.id)
        elif key.endswith(".port"):
            port = re.fullmatch(r"(?:порт\s*[:=]?\s*)?([0-9]{1,5})", normalized)
            if port and 1 <= int(port[1]) <= 65535:
                session = apply_answer(session, key, int(port[1]))
            elif explicit or len(normalized.split()) <= 4:
                raise FormAnswerError("Укажите порт числом от 1 до 65535 или выберите «Не знаю».")
            else:
                return None
        elif key.startswith("file_checks:") or key.endswith((".source_checks", ".target_checks")):
            if normalized == "без проверок":
                value = []
            else:
                value = _norm_checks([part.strip() for part in answer.split(",")])
            session = apply_answer(session, key, value)
        elif key.endswith((".source_methods", ".target_methods")):
            sending = key.endswith(".source_methods")
            modes = {
                "manual": "вручную по sftp" if sending else "заберёт человек вручную",
                "USB": "usb" if sending else "на флешку",
                "PULL": "pull",
                "PUSH": "автоматически в хранилище",
            }
            mode = next((name for name, option in modes.items() if normalized == option), None)
            protocol = re.search(r"\b(?:SFTP|SMB|FTP)\b", normalized, re.I)
            if mode is None:
                if not protocol and re.search(r"\busb\b|флешк", normalized):
                    mode = "USB"
                elif re.search(r"\bpull\b", normalized):
                    mode = "PULL"
                elif re.search(r"\bpush\b", normalized):
                    mode = "PUSH"
                elif re.search(r"\bвручную\b", normalized) and protocol and protocol[0].upper() == "SFTP":
                    mode = "manual"
            if mode is None:
                if explicit:
                    raise FormAnswerError(f"Укажите способ передачи. {question['text']}")
                return None
            if (mode == "PULL" and not sending) or (mode == "PUSH" and sending):
                raise FormAnswerError("PULL выполняет забор на отправляющей стороне, PUSH доставляет файлы получателю.")
            if mode == "USB" and not {"USB", "На флешку"}.intersection(question["options"]):
                raise FormAnswerError("USB доступен только на Узле А со стороны открытой сети. Выберите способ для этой стороны.")
            method = {"mode": mode}
            if protocol:
                method["protocol"] = protocol[0].upper()
            session = apply_answer(session, key, [method])
        elif key.endswith(".storage_mapping"):
            routes = [re.split(r"\s*(?:→|->)\s*", line)
                      for line in re.split(r"[;\n]", answer) if line.strip()]
            if not routes or any(len(pair) != 2 or not all(part.strip() for part in pair) for pair in routes):
                raise FormAnswerError("Укажите пары в формате «источник → получатель», разделяя пары точкой с запятой.")
            try:
                session = apply_answer(session, key, routes)
            except ValueError as error:
                raise FormAnswerError(str(error)) from None
        elif key.endswith(".access_groups"):
            groups = list(dict.fromkeys(
                part.strip() for part in re.split(r"[,;\n]", answer) if part.strip()
            ))
            if len({part.casefold() for part in groups}) < 2:
                if explicit:
                    raise FormAnswerError("Введите названия хотя бы двух групп через запятую или выберите «Не знаю».")
                return None
            session = apply_answer(session, key, groups)
        elif key.endswith(".access_group") and normalized == "нет":
            session = apply_answer(session, key, False)
        elif key.endswith(".access_group") and (
            normalized == "да" or "разделение доступа не требует" in normalized
        ):
            session = apply_answer(session, key, "shared")
            if session.manual_file_users is None and "один подрядчик" in normalized:
                session = session.model_copy(update={"manual_file_users": ["contractor"]})
        elif key.endswith(".recipient") and normalized.rstrip(".!?") in (
            "одна", "одна система", "один", "один получатель", "несколько", "несколько систем"
        ):
            continue
        elif key.endswith((".recipient", ".source_device", ".storage")):
            if not explicit and (
                not is_recipient_reply(answer) or len(normalized.split()) > 8
                or re.search(r"\b(?:отправля\w*|переда\w*|получает|подключ\w*|связать|добав\w*)\b", normalized)
            ):
                return None
            session = apply_answer(session, key, answer.strip())
        elif key.endswith(".protocol"):
            protocol = protocol_name(answer.strip())
            supported = ("SFTP", "FTP", "SMB") if "_methods." in key else PROTOCOLS
            if protocol.upper() not in {option.upper() for option in supported}:
                if explicit:
                    raise FormAnswerError("Укажите протокол из списка или выберите «Не знаю».")
                return None
            session = apply_answer(session, key, protocol.upper() if "_methods." in key else protocol)
        elif key.endswith(".payload") and normalized in ("файлы", "резервные копии", "журналы", "телеметрия", "время"):
            session = apply_answer(session, key, "files" if normalized in ("файлы", "резервные копии") else "data")
        elif key.endswith(".direction") and normalized.startswith(("нет", "да")):
            session = apply_answer(session, key, "one_way" if normalized.startswith("нет") else "two_way")
        else:
            return None
    return session


def attach_rule_devices(result, rule_details):
    """Link named endpoints to diagrams without changing rule computation."""
    devices = list(result["devices"])
    by_name = {(device["network_id"], device["name"].casefold()): device["id"] for device in devices}
    used_ids = {device["id"] for device in devices}
    next_id = 1

    for rule in result["rules"]:
        details = rule_details[rule["id"]]
        for side in ("from", "to"):
            name = details.get(f"{side}_device_name")
            network_id = rule[side]
            methods = details.get("methods", {}).get(network_id, [])
            if any(method["mode"] == "USB" for method in methods):
                continue
            automatic_mode = "PULL" if side == "from" else "PUSH"
            storage = next((method["storage"] for method in methods
                            if method["mode"] == automatic_mode and method.get("storage")), None)
            if storage:
                name = storage
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            key = (network_id, name.casefold())
            if key not in by_name:
                while f"device-{next_id}" in used_ids:
                    next_id += 1
                device_id = f"device-{next_id}"
                used_ids.add(device_id)
                by_name[key] = device_id
                devices.append({"id": device_id, "network_id": network_id, "name": name})
            rule[f"{side}_device_id"] = by_name[key]
    result["devices"] = devices


def apply_deferred_file_details(session, questions, message):
    """Apply explicitly named storage and headcount in the same reply."""
    ids = {question["id"] for question in questions}
    storage_ids = [key for key in ids if key.endswith(".storage")]
    known_fields = set(storage_ids) | {"manual_users_count"}
    if len(storage_ids) != 1 or ids - known_fields:
        return None
    storage = re.match(r"\s*хранилище\s*[—–:=]\s*([^.!?\n]+)", message, re.I)
    if storage is None:
        return None
    updated = apply_answer(session, storage_ids[0], storage[1].strip())
    people = re.search(
        r"\b([0-9]{1,9}|один|одна|два|две|три|четыре|пять)\s+"
        r"(?:сотрудни\w*|человек\w*|файлов\w*\s+пользовател\w*)\b", message, re.I,
    )
    if "manual_users_count" in ids and people:
        count = manual_user_count(people[1].casefold())
        updated = apply_answer(updated, "manual_users_count", count)
    return updated


def unchanged_reply(session_id, text, questions=None):
    return {
        "text": text,
        "questions": questions or [],
        "result_unchanged": True,
        "usage": build_usage(journal, session_id),
    }


def network_limit_reply(session_id, previous, text):
    if previous is not None:
        return unchanged_reply(session_id, text, shown_questions.get(session_id))
    result = evaluate(Session(session_id=session_id))["result"]
    result.update(status="unsupported", unknowns=[], requests_for_vendor=["проектирование более двух сетей"],
                  usage=build_usage(journal, session_id), timing=build_timing(journal, session_id))
    return {"text": text, "explanation": text, "questions": [], "result": result}


def reply_project_facts(outcome, questions):
    result = outcome["result"]
    rules = result["rules"][:16]
    return {
        "status": result["status"],
        "rules_count": result["rules_count"],
        "minimum_rules_count": outcome["minimum_rules_count"],
        "file_users_count": result["file_users_count"],
        "networks": result["networks"],
        "firewall": result["firewall"],
        "synonyx": result["synonyx"],
        "rules": rules,
        "rule_details": {rule["id"]: outcome["rule_details"][rule["id"]] for rule in rules},
        "questions": [question["text"] for question in questions[:6]],
    }


def respond(request, kb):
    session_id = request["session_id"]
    message = request["message"]
    turn_id = turns.get(session_id, 0) + 1
    turns[session_id] = turn_id
    previous = sessions.get(session_id)

    def wording(text, event, facts=None):
        if not MODEL_WORDING_ENABLED:
            return text
        return compose_project_reply(
            client, request["message"], text, {"event": event, **(facts or {})},
            session_id=session_id, turn_id=turn_id,
        )

    def unchanged(text, questions=None):
        return unchanged_reply(session_id, wording(text, "unchanged"), questions)

    unsupported = [item for item in detect_unsupported(message) if item != "проектирование более двух сетей"]
    antivirus_request = pending_antivirus.get(session_id)
    antivirus_declined = bool(antivirus_request and re.fullmatch(
        r"\s*(?:его\s+нет|нет(?:\s*,?\s*его нет)?|внешнего антивируса нет)[.! ]*", message, re.I,
    ))
    if antivirus_request and not unsupported and previous is None:
        scenario = re.sub(r"\bвстроенн\w*\s+антивирус\w*(?:\s+синоникса)?", "отклонённой проверкой",
                          antivirus_request, flags=re.I)
        message = scenario + "\nУточнение пользователя: " + message
        if antivirus_declined:
            message += "\nСпособ проверки файлов пока не согласован."
        else:
            message += "\nИзвлеки только подтверждённые способы проверки файлов."
    if unsupported:
        reason = ("Встроенный антивирус недоступен. Есть ли у вас внешний антивирус для проверки по ICAP? Если его нет, для файлов можно задать маску имени, тип и размер."
                  if any("антивирус" in item.casefold() for item in unsupported)
                  else "Запрошенные функции не поддерживаются: " + ", ".join(unsupported) + ".")
        if any("антивирус" in item for item in unsupported):
            pending_antivirus[session_id] = message
        if any("подсеть" in item for item in unsupported):
            reason += " Укажите конкретные системы и нужные потоки обмена."
        text = wording(reason, "unsupported")
        if previous is not None:
            return unchanged_reply(session_id, text, shown_questions.get(session_id))
        result = evaluate(Session(session_id=session_id, requests_for_vendor=unsupported))["result"]
        result.update(status="unsupported", unknowns=[], usage=build_usage(journal, session_id),
                      timing=build_timing(journal, session_id))
        return {"text": text, "explanation": reason, "questions": [], "result": result}
    pending = shown_questions.get(session_id, [])
    submitted_answers = request.get("answers")
    if submitted_answers is not None:
        if previous is None:
            return unchanged_reply(session_id, "Сервер перезапустился. Откройте новую сессию и отправьте описание обмена.")
        by_id = {question["id"]: question for question in pending}
        if not isinstance(submitted_answers, dict) or not submitted_answers or any(
            key not in by_id or not isinstance(value, str) or not value.strip()
            for key, value in submitted_answers.items()
        ):
            return unchanged_reply(session_id, "Эти уточнения уже изменились. Используйте последнюю карточку.", pending)
    form_reply = submitted_answers is not None or is_form_reply(pending, message)
    direction_ids = [question["id"] for question in pending if question["id"].endswith(".file_directions")]
    direction_question = direction_ids[0] if len(direction_ids) == 1 else None
    direction_answer = None
    direction_context = previous
    if direction_question and submitted_answers is not None:
        response_text = submitted_answers.get(direction_question)
        if response_text and response_text.strip().casefold() not in ("не знаю", "неизвестно", "я не знаю"):
            other_answers = [(by_id[key], value) for key, value in submitted_answers.items()
                             if key != direction_question]
            try:
                direction_context = apply_question_answers(previous, other_answers, explicit=True)
            except FormAnswerError as error:
                return unchanged_reply(session_id, str(error), pending)
            if direction_context is None:
                return unchanged_reply(session_id, "Проверьте ответы в карточке уточнений.", pending)
            direction_answer = response_text
    elif direction_question and not form_reply and (
        len(pending) == 1 or re.search(r"\bиз\s+[^.!?]{1,65}\s+в\s+|\bобратн\w*\s+направлен", message, re.I)
    ) and message.strip().casefold() not in ("не знаю", "неизвестно", "я не знаю"):
        direction_answer = message

    refers_to_project = previous is not None and re.search(
        r"\b(?:текущ\w*|здесь|получил\w*|у\s+нас|(?:в|на)\s+схем\w*)\b", message, re.I,
    )
    if not form_reply and FACT_QUESTION.search(message) and not refers_to_project:
        answer, hits = answer_fact(client, message, kb=kb, session_id=session_id, turn_id=turn_id)
        return {"text": answer, "sources": [
            {"file": hit["file"], "section": hit["section"]} for hit in hits
        ], "result_unchanged": previous is not None, "usage": build_usage(journal, session_id)}
    if previous is not None and ACKNOWLEDGEMENT.fullmatch(message):
        text = ("Когда будете готовы, ответьте на уточнение."
                if pending else "Текущая схема сохранена.")
        return unchanged_reply(session_id, text, pending)
    detailed = wants_detailed_explanation(message)
    if previous is not None and not form_reply and (is_project_question(message) or detailed):
        text = explain_current_project(previous, message, pending)
        if MODEL_WORDING_ENABLED:
            facts = reply_project_facts(evaluate(previous), pending)
            facts["methodology"] = (
                "Число правил для данных зависит от направления и режима, получателя, протокола и порта. "
                "Разные отправители могут использовать одно правило и остаются отдельными устройствами. NTP считается одним "
                "однонаправленным правилом. Для файлов учитываются совместимость методов передачи, "
                "профили проверок и разделение доступа."
            )
            text = wording(text, "project_question", facts)
        return unchanged_reply(session_id, text, pending)

    result_visible = request.get("current_result", True) is not None
    restoring = (
        not result_visible and previous is not None
        and message.strip() == last_project_messages.get(session_id)
    )
    session = previous if restoring else None
    edit = None if restoring or form_reply else edit_project(previous, message, client, turn_id)
    pending_edit = pending_edits.get(session_id)
    adding = not form_reply and bool(ADD_FLOW_REQUEST.match(message))
    if edit is None and not restoring and not form_reply and pending_edit and previous and not adding and is_recipient_reply(message):
        edit = continue_project_edit(previous, pending_edit, message)
    edit_text = None
    if edit is not None:
        session, edit_text, *question = edit
        pending_edits.pop(session_id, None)
        if question and question[0]:
            pending_edits[session_id] = question[0]
        if session is previous or session is None:
            return unchanged(edit_text, pending)
    if session is None and previous is not None:
        if not previous.flows and "flows" in previous.unknown_answers and not pending:
            adding = True
        if not pending and not adding and not previous.unknown_answers:
            return unchanged("Текущая схема сохранена. Укажите, что уточнить, добавить или изменить.")
        if pending and not adding and direction_answer is None:
            try:
                if submitted_answers is not None:
                    answered = [(by_id[key], value) for key, value in submitted_answers.items()]
                    session = apply_question_answers(previous, answered, explicit=True)
                else:
                    session = apply_form(previous, pending, message)
            except FormAnswerError as error:
                return unchanged_reply(session_id, str(error), pending)
            if session is None and form_reply:
                return unchanged_reply(
                    session_id, "Часть уточнений пока не удалось применить. Проверьте варианты ответа.", pending,
                )
            if session is None and len(pending) > 1 and re.fullmatch(r"\s*[0-9]+\s*", message):
                return unchanged_reply(session_id, "Введите число в нужном вопросе, чтобы я понял, к чему оно относится.", pending)
        if session is None and not pending and not adding and previous.unknown_answers:
            deferred = evaluate(previous)["deferred_questions"]
            session = apply_deferred_file_details(previous, deferred, message)
            if session is None and len(deferred) == 1:
                only = deferred[0]
                selected = any(
                    message.strip().casefold() == option.casefold()
                    for option in only["options"] if option not in ("Не знаю", "Другое")
                )
                if selected or only["id"].endswith(".storage") or (
                    only["id"] == "manual_users_count" and manual_user_count(message.strip().casefold()) is not None
                ):
                    session = apply_form(previous, deferred, message)
    if session is None:
        if direction_answer is not None:
            message = direction_answer
        full_message = message
        context = previous
        focus = None
        if previous and not adding:
            unresolved = evaluate(previous)["result"]["unknowns"]
            incomplete = [flow for flow in previous.flows if any(k.startswith(flow.id + ".") for k in unresolved)]
            if len(incomplete) == 1 and incomplete[0].payload == "files":
                focus = incomplete[0]
                context = previous.model_copy(update={"flows": [focus]})
        if previous is not None:
            full_message = (
                "Текущая согласованная конфигурация (Session JSON):\n"
                + project_context(context)
                + "\nСохрани все явно не изменённые параметры, включая id сетей и потоков. "
                  "В выходных flows верни id каждого существующего потока. "
                  "Поля Session source_network_id/target_network_id — это from/to, "
                  "payload files — type file, direction one_way/two_way — mode one-way/two-way. "
                  "kind сети — trust. Не создавай дубли существующих потоков."
                + "\nНовое сообщение пользователя:\n" + message
            )
        if direction_answer is not None:
            full_message += ("\nЭто уточнение двустороннего файлового обмена. "
                             "Сохрани согласованные поля прямого потока и верни отдельный one-way поток для обратной передачи.")
        elif focus:
            full_message += ("\nЭто ответ про один файловый поток " + focus.id +
                             ". Верни только этот поток с указанными пользователем методами и проверками. "
                             "Сохрани id сетей и направления из конфигурации. Хранилище и сервер — устройства внутри сети.")
        slots = extract(client, full_message, session_id=session_id, turn_id=turn_id,
                        evidence_text=message)
        if slots.get("_fallback"):
            text = "Модель не смогла извлечь параметры. Повторите запрос."
            if "RateLimitError" in slots.get("_warning", ""):
                text = "Groq достиг лимита запросов или токенов. Повторите через минуту."
            if previous is not None:
                return unchanged_reply(session_id, text, pending)
            return {"text": text, "result": None}
        network_names = {
            str(n.get("name") or n.get("id")).strip().casefold()
            for n in slots.get("networks", []) if isinstance(n, dict)
        }
        if len(network_names) > 2:
            # Ask the extractor to verify the boundary if it may have counted systems as networks.
            review = extract(
                client,
                "Перепроверь сетевые сегменты в запросе ниже. В первом разборе получились "
                + ", ".join(sorted(network_names))
                + ". Определи по тексту, какие из них действительно отдельные сети. "
                "Принадлежащие одной сети отделы, устройства и получатели файлов оставь в их сети. "
                "Если сетей больше двух, перечисли их все. Верни полный исправленный JSON.\n"
                + full_message,
                session_id=session_id, turn_id=turn_id, evidence_text=message,
            )
            if review.get("_fallback") or len(review["networks"]) > 2:
                limit = ("Один «Синоникс» связывает две сети. В запросе их больше двух. "
                         "Выберите одну пару и укажите, какую сеть нужно защитить.")
                return network_limit_reply(session_id, previous, wording(limit, "unsupported"))
            slots = review
        for flow in slots.get("flows", []):
            if antivirus_declined and flow.get("type") == "file":
                for field in ("source_checks", "target_checks"):
                    agreed_checks = [
                        check for check in flow.get(field) or []
                        if "icap" not in check.casefold() and "антивирус" not in check.casefold()
                        and check.casefold() in antivirus_request.casefold()
                    ]
                    flow[field] = agreed_checks or None
            port = flow.get("port")
            if isinstance(port, str):
                flow["port"] = int(port) if port.isdecimal() else None
            for field in ("source_methods", "target_methods"):
                for method in flow.get(field) or []:
                    mode = method.get("mode", "")
                    method["mode"] = "manual" if mode.casefold() == "manual" else mode.upper()
                    if method.get("trigger") not in ("arrival", "schedule"):
                        method["trigger"] = None
        if focus and len(slots.get("flows", [])) == 1 and slots["flows"][0].get("type") == "file":
            item = slots["flows"][0]
            item["id"] = focus.id
            slots["networks"] = [{"id": n.id, "name": n.name, "trust": n.kind} for n in previous.networks]
            for key, value in (("from", focus.source_network_id), ("to", focus.target_network_id), ("recipient", focus.recipient)):
                if value is not None:
                    item[key] = value
        session = session_from_extraction(session_id, slots)
        if antivirus_request:
            session.requests_for_vendor.extend(detect_unsupported(antivirus_request))
            pending_antivirus.pop(session_id, None)
        if previous is not None:
            if direction_answer is not None:
                flow_id = direction_question.removesuffix(".file_directions")
                resolved = resolve_file_directions(direction_context, session, flow_id)
                if resolved is None:
                    return unchanged("Укажите, как отправляются и куда доставляются файлы в обратном направлении.", pending)
                session = resolved
            else:
                session = merge_project_extraction(previous, session, allow_addition=adding)
            if session == previous:
                return unchanged("Не удалось определить новые параметры. Уточните исходный поток и требование.", pending)
    outcome = evaluate(session)
    if previous is not None:
        previous_outcome = evaluate(previous)
        issues = [issue for issue in outcome["issues"] if issue not in previous_outcome["issues"]]
        if issues:
            return unchanged("Изменение не применено. " + " ".join(issues), pending)
    if not restoring:
        pending_edits.pop(session_id, None)
    sessions[session_id] = session
    last_project_messages[session_id] = message.strip()
    result = outcome["result"]
    attach_rule_devices(result, outcome["rule_details"])
    for rule in result["rules"]:
        details = outcome["rule_details"][rule["id"]]
        if rule["type"] == "file":
            rule["methods_by_node"] = details["methods"]
            rule["checks_by_node"] = details["checks_by_node"]
            if any(m["mode"] == "USB" for methods in details["methods"].values() for m in methods):
                rule["transport"] = "usb"
    questions = [dict(question) for question in outcome["questions"]]
    flows_by_id = {flow.id: flow for flow in session.flows}
    network_names = {network.id: network.name for network in session.networks}
    file_flows = [flow for flow in session.flows if flow.payload == "files"]
    for question in questions:
        flow_id, _, field = question["id"].rpartition(".")
        flow = flows_by_id.get(flow_id)
        if flow is None and any(marker in question["id"] for marker in (".source_methods.", ".target_methods.")):
            flow_id = re.split(r"\.(?:source|target)_methods\.", question["id"], maxsplit=1)[0]
            flow = flows_by_id.get(flow_id)
        if flow and flow.payload == "files":
            name = flow.description or flow.recipient or "Файловый обмен"
            if len(file_flows) > 1 and flow.source_network_id and flow.target_network_id:
                source_name = network_names[flow.source_network_id]
                target_name = network_names[flow.target_network_id]
                name = f"{source_name} → {target_name} · {name}"
            label = question["text"].removeprefix(f"Поток {flow_id}. ")
            if field == "source_methods":
                label = "Как файлы попадут в «Синоникс»?"
            elif field == "target_methods":
                label = "Как файлы поступят к получателю?"
            question["text"] = f"«{name}». {label}"
        if field == "port" and flow and flow.recipient:
            question["text"] = f"На какой порт системы «{flow.recipient}» поступает трафик по {flow.protocol}?"

    methods = [q for q in questions if q["id"].endswith((".source_methods", ".target_methods"))]
    if len(methods) >= 4 and len({q["id"].rsplit(".", 1)[0] for q in methods}) >= 2:
        questions = methods + [q for q in questions if q["id"] in ("networks", "protected_network_id")]
    # The frontend adds its own “Не знаю” and “Другое” buttons.
    questions = [
        {**q, "options": [option for option in q["options"] if option not in ("Не знаю", "Другое")]}
        for q in questions
    ]
    if restoring:
        questions = pending
    # Batch answers from the current frontend include the displayed question text.
    shown_questions[session_id] = questions
    text = f"Рассчитано правил: {result['rules_count']}."
    if previous is not None:
        previous_count = previous_outcome["result"]["rules_count"]
        changes = describe_changes(previous, session) if edit_text is None else []
        if edit_text or (result_visible and changes):
            summary = edit_text or " ".join(changes)
            count = result["rules_count"]
            count_text = (f"Число правил осталось прежним: {count}." if count == previous_count
                          else f"Число правил изменилось: {previous_count} → {count}.")
            text = f"{summary} {count_text}"
        elif result_visible and previous == session and not questions:
            text += " Текущая схема уже учитывает эти параметры."
    if previous is not None and session.manual_users_count != previous.manual_users_count:
        text += f" Пользователей ручной передачи — {session.manual_users_count}."
    if outcome["minimum_rules_count"] > result["rules_count"]:
        minimum = outcome["minimum_rules_count"]
        estimate = "Предварительная оценка: минимум 1 правило." if minimum == 1 else (
            f"Предварительная оценка по числу правил: минимум {minimum}."
        )
        text = f"{text} {estimate}" if result["rules_count"] or (previous is not None and previous != session) else estimate
        if outcome["minimum_rules_reason"]:
            text += " " + outcome["minimum_rules_reason"]
    if not result["rules_count"] and not outcome["minimum_rules_count"] and result["unknowns"] and not outcome["issues"]:
        text = "Пока недостаточно сведений для расчёта правил."
        if not questions and "flows" in result["unknowns"]:
            text += " Когда появятся сведения об обмене, опишите, что нужно передать, откуда и куда."
    deferred_text = ""
    if outcome["deferred_questions"] and not questions and result["status"] != "unsupported":
        remaining = []
        for question in outcome["deferred_questions"]:
            flow_id, _, field = question["id"].rpartition(".")
            flow = flows_by_id.get(flow_id)
            label = question["text"]
            if flow:
                label = label.removeprefix(f"Поток {flow_id}. ")
                label = f"«{flow.description or flow.recipient or flow_id}». {label}"
            if field == "target_methods":
                label += " Укажите способ доставки, а для автоматической доставки — протокол и хранилище."
            remaining.append(f"- {label}")
        deferred_text = "\n\nОсталось уточнить.\n\n" + "\n".join(remaining)
    if questions:
        if result["rules_count"] and all(q["id"].startswith("file_checks:") for q in questions):
            text += " Осталось согласовать настройки проверки файлов."
        else:
            text += " Для завершения расчёта нужны уточнения."
    if outcome["issues"]:
        text += "\n" + "\n".join(outcome["issues"])
    if MODEL_WORDING_ENABLED and not restoring:
        facts = reply_project_facts(outcome, questions)
        if previous is not None and previous != session:
            facts["previous_rules"] = previous_outcome["result"]["rules"][:16]
            facts["previous_rules_count"] = previous_count
            facts["previous_status"] = previous_outcome["result"]["status"]
        event = ("unsupported" if result["status"] == "unsupported" else
                 "updated" if previous is not None and previous != session else "calculated")
        text = wording(text, event, facts)
    text += deferred_text
    result["usage"] = build_usage(journal, session_id)
    result["timing"] = build_timing(journal, session_id)
    explanation = "\n\n".join(filter(None, (explain_placement(result) if result["synonyx"] and result["firewall"] else "", explain_rules(result["rules"], result["networks"]))))
    return {"text": text, "questions": questions, "result": result, "explanation": explanation}


MAX_CHAT_REQUEST_BYTES = 1024 * 1024
SESSION_LOCKS = tuple(Lock() for _ in range(64))


def read_chat_request(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if not 0 < length <= MAX_CHAT_REQUEST_BYTES:
        raise ValueError("Недопустимый размер запроса.")
    request = json.loads(handler.rfile.read(length))
    if not isinstance(request, dict):
        raise ValueError("Запрос должен быть JSON-объектом.")
    session_id = request.get("session_id")
    if not isinstance(session_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", session_id):
        raise ValueError("Недопустимый идентификатор сессии.")
    message = request.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Введите сообщение.")
    return request


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        try:
            request = read_chat_request(self)
        except (ValueError, UnicodeError):
            self.send_error(400, "Invalid chat request")
            return

        try:
            session_id = request["session_id"]
            with SESSION_LOCKS[hash(session_id) % len(SESSION_LOCKS)]:
                try:
                    response = respond(request, kb)
                finally:
                    save_session(journal, session_id)
        except GroqRateLimit as error:
            data = json.dumps({"detail": str(error)}, ensure_ascii=False).encode("utf-8")
            self.send_response(429)
            self.send_header("Retry-After", str(error.retry_after))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        except Exception as exc:
            print(f"chat failed: {type(exc).__name__} ({getattr(exc, 'status_code', None)})", flush=True)
            if hasattr(exc, "errors"):
                print(exc.errors(include_input=False, include_context=False), flush=True)
            self.send_error(502, "Chat request failed")
            return
        calls = journal.calls(request["session_id"])
        if calls and calls[-1].turn_id == turns.get(request["session_id"]):
            record = calls[-1]
            print(f"provider={client.provider} purpose={record.purpose} response_id={record.provider_response_id}", flush=True)
        data = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    global client, kb
    client = LLMClient(journal)
    if client.provider != "groq" or not client.api_key:
        raise SystemExit("Configure LLM_PROVIDER=groq and GROQ_API_KEY in the local .env.")

    archive_setting = os.environ.get("SYNONYX_CASE_ZIP")
    if os.environ.get("SYNONYX_BASE_DIR") or not archive_setting:
        problem = llm_config.knowledge_base_problem()
        if problem:
            raise SystemExit(problem)
        kb = KnowledgeBase(llm_config.SYNONYX_BASE_DIR)
    else:
        archive = Path(archive_setting).expanduser()
        if not archive.is_file():
            raise SystemExit("SYNONYX_CASE_ZIP must point to an existing ZIP file.")
        with TemporaryDirectory(dir=os.environ.get("SYNONYX_TEMP_DIR")) as directory, ZipFile(archive) as source:
            for member in source.namelist():
                path = Path(member)
                if path.parent.as_posix() == "synonyx_base" and path.suffix == ".md":
                    (Path(directory) / path.name).write_bytes(source.read(member))
            if not any(Path(directory).glob("*.md")):
                raise SystemExit("В архиве отсутствуют материалы synonyx_base/*.md.")
            kb = KnowledgeBase(directory)

    port = int(os.environ.get("SYNONYX_API_PORT", "8000"))
    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"Groq fact/project test API on http://127.0.0.1:{port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
