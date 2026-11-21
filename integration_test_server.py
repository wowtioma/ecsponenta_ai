import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from llm import Journal, KnowledgeBase, LLMClient, answer_fact, build_timing, build_usage, extract
from llm import detect_unsupported, save_session
from llm.answer import explain_placement, explain_rules
from llm.client import GroqRateLimit
from llm.extract import _norm_checks
from llm import prompts

prompts.SYSTEM_EXTRACT += """
Для файловых потоков дополнительно верни source_methods и target_methods:
массив объектов {mode, protocol, storage, trigger}. mode: manual, USB, PULL,
PUSH. Указывай способы, протоколы и хранилища, подтверждённые запросом.
source_checks и target_checks: массив проверок для каждой стороны или null,
если сторона не определена. Пустой массив означает явно согласованное отсутствие.
access_group: shared при общем доступе или одном передающем пользователе,
иначе null или явно указанная группа. На верхнем уровне manual_file_users:
список явно упомянутых людей, которые передают файлы вручную или на USB.
Для синхронизации времени по NTP с UDP укажи application_protocol: NTP.
Имя получателя (например «NTP-сервер») само по себе не определяет протокол потока.
Фраза «на один сервер в офисе» уже описывает роль получателя. Заполни recipient
как «сервер в офисе», даже если нет имени машины или IP-адреса.
Укажи USB, если человек приносит файл на флешке, а не загружает его по сети.
В этом случае from — идентификатор открытой сети, к которой обращён Узел А.
Для PUSH при поступлении файла укажи trigger: arrival. При явно указанном
внешнем антивирусе без стороны сохрани требование в checks, стороны оставь null.
"""

prompts.SYSTEM_FACT += (
    "\nИсточник интерфейс показывает отдельно из метаданных поиска. "
    "В тексте ответа не указывай файл, номер раздела или строку «Источник»."
)

from b_adapter import session_from_extraction
from rules import Session, apply_answer, evaluate, record_unresolved_answer
from project_edits import (
    continue_project_edit, describe_changes, edit_project, is_recipient_reply, project_context,
)
from project_dialogue import (
    ACKNOWLEDGEMENT, ADD_FLOW_REQUEST, explain_current_project, is_project_question, merge_project_extraction,
)

journal = Journal()
sessions = {}
last_project_messages = {}
shown_questions = {}
pending_edits = {}
turns = {}
client: LLMClient | None = None

FACT_QUESTION = re.compile(r"^\s*(?:сколько\s+правил\b|зачем\s+(?:нужен\s+)?(?:межсетевой экран|мэ)\b)", re.I)


class FormAnswerError(ValueError):
    pass


def apply_form(session, questions, message):
    explicit = message.strip().startswith(questions[0]["text"] + " ")
    if len(questions) == 1 and not explicit:
        if "\n" in message or len(message) > 180:
            return None
        answers = [message.strip()]
    else:
        pattern = r"\A" + r"\n".join(
            re.escape(question["text"]) + r" (.+?)" for question in questions
        ) + r"\Z"
        match = re.match(pattern, message.strip(), flags=re.S)
        if match is None:
            return None
        answers = match.groups()

    for question, answer in zip(questions, answers):
        key = question["id"]
        normalized = answer.strip().casefold().rstrip(".!")
        if normalized in ("не знаю", "я не знаю", "неизвестно", "null"):
            session = record_unresolved_answer(session, key)
        elif key.endswith("_network_id"):
            network_id = next((n.id for n in session.networks if normalized in (n.id.casefold(), n.name.casefold())), None)
            if network_id is None:
                session = record_unresolved_answer(session, key, answer)
            else:
                session = apply_answer(session, key, network_id)
        elif key.endswith(".port"):
            port = re.fullmatch(r"(?:порт\s*[:=]?\s*)?([0-9]{1,5})", normalized)
            if port and 1 <= int(port[1]) <= 65535:
                session = apply_answer(session, key, int(port[1]))
            elif explicit or len(normalized.split()) <= 4:
                raise FormAnswerError("Укажите порт числом от 1 до 65535 или выберите «Не знаю».")
            else:
                return None
        elif key.endswith((".source_checks", ".target_checks")):
            if normalized == "без проверок":
                value = []
            else:
                value = _norm_checks([part.strip() for part in answer.split(",")])
            session = apply_answer(session, key, value)
        elif key.endswith((".source_methods", ".target_methods")):
            mode = {
                "вручную по sftp": "manual", "заберёт человек вручную": "manual",
                "usb": "USB", "на флешку": "USB", "pull": "PULL",
                "автоматически в хранилище": "PUSH",
            }.get(normalized)
            if mode is None:
                return None
            session = apply_answer(session, key, [{"mode": mode}])
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
        elif key.endswith((".recipient", ".storage")):
            if not explicit and (
                not is_recipient_reply(answer) or len(normalized.split()) > 8
                or re.search(r"\b(?:отправля\w*|переда\w*|получает|подключ\w*|связать|добав\w*)\b", normalized)
            ):
                return None
            session = apply_answer(session, key, answer.strip())
        elif key.endswith(".protocol") and answer.strip().upper() in ("TCP", "UDP", "SMB", "FTP", "SFTP", "MQTT", "NTP"):
            session = apply_answer(session, key, answer.strip().upper())
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


def unchanged_reply(session_id, text, questions=None):
    return {
        "text": text,
        "questions": questions or [],
        "result_unchanged": True,
        "usage": build_usage(journal, session_id),
    }


def respond(request, kb):
    session_id = request["session_id"]
    message = request["message"]
    turn_id = turns.get(session_id, 0) + 1
    turns[session_id] = turn_id
    previous = sessions.get(session_id)
    unsupported = detect_unsupported(message)
    if unsupported:
        reason = ("Встроенный антивирус недоступен. Проверку можно выполнить внешним антивирусом по ICAP."
                  if any("антивирус" in item.casefold() for item in unsupported)
                  else "Запрошенные функции не поддерживаются: " + ", ".join(unsupported) + ".")
        if previous is not None:
            return {"text": reason + " Конфигурация сохранена без изменений.",
                    "result_unchanged": True}
        result = evaluate(Session(session_id=session_id, requests_for_vendor=unsupported))["result"]
        result["status"] = "unsupported"
        return {"text": reason, "result": result}
    refers_to_project = previous is not None and re.search(
        r"\b(?:текущ\w*|здесь|получил\w*|у\s+нас|(?:в|на)\s+схем\w*)\b", message, re.I,
    )
    if FACT_QUESTION.search(message) and not refers_to_project:
        answer, hits = answer_fact(client, message, kb=kb, session_id=session_id, turn_id=turn_id)
        return {"text": answer, "sources": [
            {"file": hit["file"], "section": hit["section"]} for hit in hits
        ], "result_unchanged": previous is not None, "usage": build_usage(journal, session_id)}
    pending = shown_questions.get(session_id, [])
    if previous is not None and ACKNOWLEDGEMENT.fullmatch(message):
        text = ("Когда будете готовы, ответьте на уточнение."
                if pending else "Текущая схема сохранена.")
        return unchanged_reply(session_id, text, pending)
    if previous is not None and is_project_question(message):
        return unchanged_reply(session_id, explain_current_project(previous, message, pending), pending)

    result_visible = request.get("current_result", True) is not None
    restoring = (
        not result_visible and previous is not None
        and message.strip() == last_project_messages.get(session_id)
    )
    session = previous if restoring else None
    edit = None if restoring else edit_project(previous, message, client, turn_id)
    pending_edit = pending_edits.get(session_id)
    adding = bool(ADD_FLOW_REQUEST.match(message))
    if edit is None and not restoring and pending_edit and previous and not adding and is_recipient_reply(message):
        edit = continue_project_edit(previous, pending_edit, message)
    edit_text = None
    if edit is not None:
        session, edit_text, *question = edit
        pending_edits.pop(session_id, None)
        if question and question[0]:
            pending_edits[session_id] = question[0]
        if session is previous or session is None:
            return unchanged_reply(session_id, edit_text, pending)
    if session is None and previous is not None:
        if not pending and not adding:
            return unchanged_reply(
                session_id, "Текущая схема сохранена. Укажите, что уточнить, добавить или изменить.",
            )
        if pending and not adding:
            try:
                session = apply_form(previous, pending, message)
            except FormAnswerError as error:
                return unchanged_reply(session_id, str(error), pending)
            if session is None and message.startswith(pending[0]["text"]):
                return unchanged_reply(
                    session_id, "Часть уточнений пока не удалось применить. Проверьте варианты ответа.", pending,
                )
            if session is None and len(pending) > 1 and re.fullmatch(r"\s*[0-9]+\s*", message):
                return unchanged_reply(session_id, "Укажите, к какому потоку относится этот порт.", pending)
    if session is None:
        full_message = message
        if previous is not None:
            full_message = (
                "Текущая согласованная конфигурация (Session JSON):\n"
                + project_context(previous)
                + "\nСохрани все явно не изменённые параметры, включая id сетей и потоков. "
                  "В выходных flows верни id каждого существующего потока. "
                  "Поля Session source_network_id/target_network_id — это from/to, "
                  "payload files — type file, direction one_way/two_way — mode one-way/two-way. "
                  "kind сети — trust. Не создавай дубли существующих потоков."
                + "\nНовое сообщение пользователя:\n" + message
            )
        slots = extract(client, full_message, session_id=session_id, turn_id=turn_id)
        if slots.get("_fallback"):
            text = "Модель не смогла извлечь параметры. Повторите запрос."
            if "RateLimitError" in slots.get("_warning", ""):
                text = "Groq достиг лимита запросов или токенов. Повторите через минуту."
            if previous is not None:
                return unchanged_reply(session_id, text, pending)
            return {"text": text, "result": None}
        for flow in slots.get("flows", []):
            port = flow.get("port")
            if isinstance(port, str):
                flow["port"] = int(port) if port.isdecimal() else None
            for field in ("source_methods", "target_methods"):
                for method in flow.get(field) or []:
                    mode = method.get("mode", "")
                    method["mode"] = "manual" if mode.casefold() == "manual" else mode.upper()
                    if method.get("trigger") not in ("arrival", "schedule"):
                        method["trigger"] = None
        session = session_from_extraction(session_id, slots)
        if previous is not None:
            session = merge_project_extraction(previous, session, allow_addition=adding)
            if session == previous:
                return unchanged_reply(
                    session_id, "Не удалось определить новые параметры. Уточните исходный поток и требование.",
                    pending,
                )
    outcome = evaluate(session)
    if previous is not None:
        previous_outcome = evaluate(previous)
        issues = [issue for issue in outcome["issues"] if issue not in previous_outcome["issues"]]
        if issues:
            return unchanged_reply(session_id, "Изменение не применено. " + " ".join(issues), pending)
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
    for question in questions:
        flow_id, _, field = question["id"].rpartition(".")
        flow = flows_by_id.get(flow_id)
        if field == "port" and flow and flow.recipient:
            question["text"] = f"На какой порт системы «{flow.recipient}» поступает трафик по {flow.protocol}?"
        elif field in ("source_methods", "target_methods") and flow:
            description = flow.description or "Файловый обмен"
            action = ("Как файлы попадут в «Синоникс»?" if field == "source_methods"
                      else "Как файлы поступят к получателю?")
            question["text"] = f"«{description}». {action}"
    # The frontend adds its own “Не знаю” and “Другое” buttons.
    questions = [
        {**q, "options": [option for option in q["options"] if option not in ("Не знаю", "Другое")]}
        for q in questions
    ]
    # Batch answers from the current frontend include the displayed question text.
    shown_questions[session_id] = questions
    result["usage"] = build_usage(journal, session_id)
    result["timing"] = build_timing(journal, session_id)
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
    if outcome["minimum_rules_count"] > result["rules_count"]:
        minimum = outcome["minimum_rules_count"]
        estimate = "Предварительная оценка: минимум 1 правило." if minimum == 1 else (
            f"Предварительная оценка по числу правил: минимум {minimum}."
        )
        text = f"{text} {estimate}" if result["rules_count"] else estimate
    if questions:
        text += " Для завершения расчёта нужны уточнения."
    if outcome["issues"]:
        text += "\n" + "\n".join(outcome["issues"])
    explanation = "\n\n".join(filter(None, (explain_placement(result) if result["synonyx"] and result["firewall"] else "", explain_rules(result["rules"]))))
    return {"text": text, "questions": questions, "result": result, "explanation": explanation}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        try:
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            session_id = request["session_id"]
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", session_id):
                self.send_error(400, "Invalid session id")
                return
            response = respond(request, kb)
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
    if not archive_setting:
        raise SystemExit("Set SYNONYX_CASE_ZIP to the organizers' ZIP archive.")
    archive = Path(archive_setting).expanduser()
    if not archive.is_file():
        raise SystemExit("SYNONYX_CASE_ZIP must point to an existing ZIP file.")
    port = int(os.environ.get("SYNONYX_API_PORT", "8000"))
    with TemporaryDirectory() as directory, ZipFile(archive) as source:
        for member in source.namelist():
            path = Path(member)
            if path.parent.as_posix() == "synonyx_base" and path.suffix == ".md":
                (Path(directory) / path.name).write_bytes(source.read(member))
        kb = KnowledgeBase(directory)
        with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
            print(f"Groq fact/project test API on http://127.0.0.1:{port}", flush=True)
            server.serve_forever()


if __name__ == "__main__":
    main()
