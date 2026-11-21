"""Read-only project answers and safe reconciliation of newly extracted parameters."""

import re

from llm.answer import explain_placement, explain_rules
from project_edits import ADDITIONAL_RECIPIENT_REQUEST, EDIT_REQUEST
from rules import Session, evaluate

ACKNOWLEDGEMENT = re.compile(
    r"\s*(?:(?:спасибо|благодарю|понял[аи]?|понятно|хорошо|ок(?:ей)?|ясно|принято)[,!. ]*)+",
    re.I,
)
ADD_FLOW_REQUEST = re.compile(
    r"^\s*(?:(?:а|пожалуйста|давайте?)\s+)*добав\w*\b",
    re.I,
)
QUESTION_PREFIX = re.compile(
    r"^\s*(?:а\s+)?(?:почему|зачем|кто|где|сколько|как\s+(?:работает|устроен\w*|считается)|"
    r"како\w*\s+(?:порт|протокол|сервер|устройств\w*|правил\w*)|что\s+(?:означает|получилось))\b",
    re.I,
)


def is_project_question(message: str) -> bool:
    return bool(
        QUESTION_PREFIX.match(message)
        or message.rstrip().endswith("?")
        and not EDIT_REQUEST.match(message)
        and not ADDITIONAL_RECIPIENT_REQUEST.search(message)
        and not ADD_FLOW_REQUEST.match(message)
    )


def explain_current_project(session: Session, message: str, questions: list[dict]) -> str:
    if questions and re.search(r"\b(?:почему|зачем)\b.*\b(?:спрашива\w*|уточня\w*)", message, re.I):
        if any(question["id"].endswith(".recipient") for question in questions):
            return (
                "Получатель нужен для расчёта: у разных принимающих систем могут быть отдельные правила. "
                "Укажите имя или назначение системы, которая принимает данные."
            )
        if any(question["id"].endswith(".port") for question in questions):
            return (
                "Порт определяет, какое соединение нужно разрешить на стороне получателя. "
                "Укажите порт из его настроек или выберите «Не знаю»."
            )
        return "Ответ нужен, чтобы уточнить параметры обмена. " + questions[0]["text"]

    outcome = evaluate(session)
    result = outcome["result"]
    if re.search(r"\b(?:где|почему|зачем)\b.*\b(?:синоникс\w*|межсетев\w*)", message, re.I):
        if result["synonyx"] and result["firewall"]:
            return explain_placement(result)
    rules = result["rules"]
    if not rules:
        return "Готовые правила пока не рассчитаны." + (
            f" Для продолжения: {questions[0]['text']}" if questions else ""
        )

    lines = [f"В текущей схеме рассчитано правил: {len(rules)}."]
    for rule in rules:
        details = outcome["rule_details"][rule["id"]]
        recipient = details.get("to_device_name") or details.get("recipient")
        if recipient:
            protocol = details.get("application_protocol") or rule.get("protocol")
            transport = " ".join(str(value) for value in (protocol, rule.get("port")) if value is not None)
            lines.append(f"«{rule['description']}» — получатель «{recipient}»" + (f", {transport}." if transport else "."))
    if len(rules) == 1 and rules[0]["type"] == "data":
        protocol = outcome["rule_details"][rules[0]["id"]].get("application_protocol")
        if protocol == "NTP":
            lines.append("Для синхронизации времени NTP рассчитывается одно однонаправленное правило.")
        elif rules[0]["port"] is not None:
            lines.append(
                "Для этого потока достаточно одного правила: получатель, протокол и порт общие. "
                "Несколько отправителей сами по себе не увеличивают число правил."
            )
    if len(lines) == 1:
        return explain_rules(rules)
    return "\n".join(lines)


def _field(data, path):
    for component in path:
        if isinstance(data, dict):
            data = data.get(component)
        elif isinstance(data, list) and component.isdecimal() and int(component) < len(data):
            data = data[int(component)]
        else:
            return None
    return data


def _compatible(candidate, current):
    return all(
        getattr(candidate, field) is None or getattr(current, field) is None
        or getattr(candidate, field) == getattr(current, field)
        for field in ("source_network_id", "target_network_id", "payload", "recipient")
    )


def merge_project_extraction(previous: Session, extracted: Session, *, allow_addition: bool) -> Session:
    """Keep agreed values and use extraction only to complete missing slots or add flows."""
    partial = previous.model_dump()
    networks = {network.id: network for network in previous.networks}
    if len(networks) < 2:
        for network in extracted.networks:
            networks.setdefault(network.id, network)
    partial["networks"] = [network.model_dump() for network in networks.values()]

    extracted_by_id = {flow.id: flow for flow in extracted.flows}
    old_ids = {flow.id for flow in previous.flows}
    matched_ids = set()
    for old, data in zip(previous.flows, partial["flows"]):
        candidate = extracted_by_id.get(old.id)
        if candidate is None and len(previous.flows) == len(extracted.flows) == 1 and not allow_addition:
            candidate = extracted.flows[0]
        if candidate is None or not _compatible(candidate, old):
            continue
        matched_ids.add(candidate.id)
        if allow_addition:
            continue
        values = candidate.model_dump()
        for key, value in values.items():
            if key != "id" and value is not None and data[key] is None:
                if key.endswith("_network_id") and value not in networks:
                    continue
                data[key] = value
            elif key in ("source_methods", "target_methods") and value and data[key]:
                for agreed, proposal in zip(data[key], value):
                    if agreed["mode"] == proposal["mode"]:
                        for field in ("protocol", "storage", "trigger"):
                            if agreed[field] is None:
                                agreed[field] = proposal[field]

    if allow_addition or not previous.flows:
        signatures = [
            {key: value for key, value in flow.items() if key not in ("id", "description")}
            for flow in partial["flows"]
        ]
        for flow in extracted.flows:
            if flow.id in old_ids or flow.id in matched_ids:
                continue
            if any(
                network is not None and network not in networks
                for network in (flow.source_network_id, flow.target_network_id, flow.initiator_network_id)
            ):
                continue
            signature = flow.model_dump(exclude={"id", "description"})
            if signature not in signatures:
                partial["flows"].append(flow.model_dump())
                signatures.append(signature)

    if previous.manual_file_users is None and extracted.manual_file_users is not None:
        partial["manual_file_users"] = extracted.manual_file_users

    # Confirmed values supersede an earlier «Не знаю», while unanswered slots stay open.
    for key in previous.unknown_answers:
        flow = next((item for item in partial["flows"] if key.startswith(item["id"] + ".")), None)
        if flow and _field(flow, key[len(flow["id"]) + 1:].split(".")) is not None:
            partial["unknown_answers"].remove(key)
    return Session.model_validate(partial)
