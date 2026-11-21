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
Для NTP с UDP укажи application_protocol: NTP.
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

journal = Journal()
sessions = {}
project_messages = {}
shown_questions = {}
turns = {}
client = LLMClient(journal)
if client.provider != "groq" or not client.api_key:
    raise SystemExit("Configure LLM_PROVIDER=groq and GROQ_API_KEY in the local .env.")

FACT_QUESTION = re.compile(r"^\s*(?:сколько\s+правил\b|зачем\s+(?:нужен\s+)?(?:межсетевой экран|мэ)\b)", re.I)


def apply_form(session, questions, message):
    if len(questions) == 1 and not message.startswith(questions[0]["text"] + " "):
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
        normalized = answer.strip().casefold()
        if normalized in ("не знаю", "null"):
            session = record_unresolved_answer(session, key)
        elif key.endswith("_network_id"):
            network_id = next((n.id for n in session.networks if normalized in (n.id.casefold(), n.name.casefold())), None)
            if network_id is None:
                session = record_unresolved_answer(session, key, answer)
            else:
                session = apply_answer(session, key, network_id)
        elif key.endswith(".port") and normalized.isdecimal() and 1 <= int(normalized) <= 65535:
            session = apply_answer(session, key, int(normalized))
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
            session = apply_answer(session, key, answer.strip())
        elif key.endswith(".protocol") and answer.strip().upper() in ("TCP", "UDP", "SMB", "FTP", "SFTP", "MQTT", "NTP"):
            session = apply_answer(session, key, answer.strip().upper())
        elif key.endswith(".direction") and normalized.startswith(("нет", "да")):
            session = apply_answer(session, key, "one_way" if normalized.startswith("нет") else "two_way")
        else:
            return None
    return session


def respond(request, kb):
    session_id = request["session_id"]
    message = request["message"]
    turn_id = turns.get(session_id, 0) + 1
    turns[session_id] = turn_id
    unsupported = detect_unsupported(message)
    if unsupported:
        result = evaluate(Session(session_id=session_id, requests_for_vendor=unsupported))["result"]
        result["status"] = "unsupported"
        return {"text": "Встроенный антивирус недоступен. Проверку можно выполнить внешним антивирусом по ICAP."
                if any("антивирус" in item.casefold() for item in unsupported) else "Обнаружены неподдерживаемые требования.",
                "result": result}
    if FACT_QUESTION.search(message):
        answer, hits = answer_fact(client, message, kb=kb, session_id=session_id, turn_id=turn_id)
        return {"text": answer, "sources": [
            {"file": hit["file"], "section": hit["section"]} for hit in hits
        ], "result": None}
    session = None
    previous = sessions.get(session_id)
    if previous is not None:
        pending = shown_questions.get(session_id, [])
        if pending:
            session = apply_form(previous, pending, message)
            if session is None and message.startswith(pending[0]["text"]):
                return {"text": "Часть уточнений пока не удалось применить. Проверьте варианты ответа.", "questions": [
                    {**q, "options": [o for o in q["options"] if o not in ("Не знаю", "Другое")]}
                    for q in pending
                ], "result": None}
    if session is None:
        context = project_messages.get(session_id, "") if previous is not None else ""
        full_message = (context + "\nУточнение заказчика: " + message) if context else message
        slots = extract(client, full_message, session_id=session_id, turn_id=turn_id)
        if slots.get("_fallback"):
            text = "Модель не смогла извлечь параметры. Повторите запрос."
            if "RateLimitError" in slots.get("_warning", ""):
                text = "Groq достиг лимита запросов или токенов. Повторите через минуту."
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
        project_messages[session_id] = full_message
    sessions[session_id] = session
    outcome = evaluate(session)
    result = outcome["result"]
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
        except Exception as exc:
            print(f"chat failed: {type(exc).__name__} ({getattr(exc, 'status_code', None)})", flush=True)
            if hasattr(exc, "errors"):
                print(exc.errors(include_input=False, include_context=False), flush=True)
            self.send_error(502, "Chat request failed")
            return
        calls = journal.calls(request["session_id"])
        if calls:
            record = calls[-1]
            print(f"provider={client.provider} purpose={record.purpose} response_id={record.provider_response_id}", flush=True)
        data = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


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
