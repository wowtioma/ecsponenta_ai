"""Read-only project answers and safe reconciliation of newly extracted parameters."""

import re

from llm.answer import explain_placement, explain_rules
from project_edits import ADDITIONAL_RECIPIENT_REQUEST, EDIT_REQUEST
from rules import Session, evaluate, flow_may_use_manual_transfer

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
            protocol = details.get("application_protocol") or (rule.get("protocol") if rule["type"] == "data" else None)
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
        return explain_rules(rules, result["networks"])
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


def resolve_file_directions(previous: Session, extracted: Session, flow_id: str) -> Session | None:
    """Turn a pending two-way description into two directed configurations."""
    original = next((flow for flow in previous.flows if flow.id == flow_id), None)
    if original is None or original.payload != "files" or original.direction != "two_way":
        return None
    from_id, to_id = original.source_network_id, original.target_network_id
    reverse_options = [
        flow for flow in extracted.flows
        if flow.payload == "files" and (flow.source_network_id, flow.target_network_id) == (to_id, from_id)
        and flow.direction == "one_way" and (flow.source_methods or flow.target_methods)
    ]
    if len(reverse_options) != 1:
        return None

    forward = original.model_copy(update={"direction": "one_way"})
    snapshot = previous.model_copy(update={
        "flows": [forward if flow.id == flow_id else flow for flow in previous.flows],
        "unknown_answers": [key for key in previous.unknown_answers if key != f"{flow_id}.file_directions"],
    })
    merged = merge_project_extraction(snapshot, extracted, allow_addition=False)
    reverse = reverse_options[0]
    signature = reverse.model_dump(exclude={"id", "description"})
    if any(flow.model_dump(exclude={"id", "description"}) == signature for flow in merged.flows):
        return merged

    ids = {flow.id for flow in merged.flows}
    reverse_id = f"{flow_id}-reverse"
    index = 2
    while reverse_id in ids:
        reverse_id = f"{flow_id}-reverse-{index}"
        index += 1
    return merged.model_copy(update={"flows": [*merged.flows, reverse.model_copy(update={"id": reverse_id})]})


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
        if not allow_addition and (candidate is None or not _compatible(candidate, old)):
            # A follow-up may contain only the file flow, renumbered by the extractor.
            options = [flow for flow in extracted.flows if _compatible(flow, old)]
            if len(options) == 1 and sum(_compatible(options[0], flow) for flow in previous.flows) == 1:
                candidate = options[0]
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
                settings = ("protocol", "storage", "trigger")
                for agreed in data[key]:
                    compatible = [
                        proposal for proposal in value
                        if agreed["mode"] == proposal["mode"] and all(
                            agreed[field] is None or proposal[field] is None or agreed[field] == proposal[field]
                            for field in settings
                        )
                    ]
                    if len(compatible) == 1:
                        for field in settings:
                            if agreed[field] is None:
                                agreed[field] = compatible[0][field]

    added = []
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
                added.append(flow)

    if any(flow.payload == "files" for flow in added):
        # Common profiles from earlier turns describe the previous set of flows.
        partial["assumptions"].pop("same_file_checks", None)
    if any(flow_may_use_manual_transfer(flow) for flow in added) and previous.flows:
        partial["manual_users_count"] = None
        if previous.manual_file_users is not None and extracted.manual_file_users:
            partial["manual_file_users"] = list(dict.fromkeys([
                *previous.manual_file_users, *extracted.manual_file_users,
            ]))
        else:
            partial["manual_file_users"] = None
        if "manual_users_count" in partial["unknown_answers"]:
            partial["unknown_answers"].remove("manual_users_count")
    elif previous.manual_file_users is None and extracted.manual_file_users is not None:
        partial["manual_file_users"] = extracted.manual_file_users

    if "manual_users_count" in partial["unknown_answers"] and partial["manual_file_users"] is not None:
        partial["unknown_answers"].remove("manual_users_count")

    # Confirmed values supersede an earlier «Не знаю», while unanswered slots stay open.
    for key in previous.unknown_answers:
        flow = next((item for item in partial["flows"] if key.startswith(item["id"] + ".")), None)
        if flow and _field(flow, key[len(flow["id"]) + 1:].split(".")) is not None:
            partial["unknown_answers"].remove(key)
    return Session.model_validate(partial)
