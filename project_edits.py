"""Apply explicit chat corrections to the current, validated project."""

import json
import logging
import re
from typing import NamedTuple

from pydantic import ValidationError

from llm.client import GroqRateLimit

from rules import Flow, PROTOCOLS, Session, TWO_WAY_PROTOCOLS, evaluate, protocol_name

EDIT_REQUEST = re.compile(
    r"^\s*(?:а\s+)?(?:пожалуйста[, ]+|можно\s+|давайте?\s+)*"
    r"(?:поменя\w*|измен\w*|замен\w*|исправ\w*|переключ\w*|"
    r"переимену\w*|убер\w*|удал\w*|постав\w*|установ\w*|сдела\w*|запрет\w*|разреш\w*)\b",
    re.I,
)
ADDITIONAL_RECIPIENT_REQUEST = re.compile(
    r"^\s*(?:а\s+)?(?:пожалуйста[, ]+|давайте?\s+)*добав\w*\s+(?:ещ[её]|втор\w*|дополнительн\w*)\b"
    r"|\b(?:ещ[её]|также|вдобавок)\s+(?:и\s+)?(?:на|в|к|для)\s+",
    re.I,
)
EXPLICIT_RECIPIENT = re.compile(
    r"\b(?:ещ[её]|также|вдобавок)\s+(?:и\s+)?(?:на|в|к|для)\s+([^\n,;!?]{1,100})$",
    re.I,
)


class RecipientQuestion(NamedTuple):
    flow_id: str
    text: str


class FlowChoice(NamedTuple):
    flow_ids: tuple[str, ...]
    port: int | None = None  # None denotes a request to remove a recipient.


REMOVE_REQUEST = re.compile(
    r"^\s*(?:а\s+)?(?:пожалуйста[, ]+|давайте?\s+|можно\s+)*"
    r"(?:убер\w*|удал\w*|исключ\w*)\s+(.+?)[.!?\s]*$",
    re.I,
)
CANCEL_REPLY = {"отмена", "не знаю", "не нужно", "отмени", "отмени правку"}


def _device_key(name: str) -> tuple[str, ...]:
    return tuple(sorted(re.findall(r"\w+", name.casefold().replace("ё", "е"))))


def _named_endpoints(session: Session):
    for flow in session.flows:
        if flow.source_device and flow.source_network_id:
            yield flow.source_device, flow.source_network_id
        if flow.recipient and flow.target_network_id:
            yield flow.recipient, flow.target_network_id


def _respect_named_recipient(session: Session, message: str, patch: dict) -> dict:
    match = EXPLICIT_RECIPIENT.search(message.strip().rstrip(".!?"))
    if match:
        target = match.group(1).strip()
        if any(_device_key(name) == _device_key(target) for name, _ in _named_endpoints(session)):
            return {**patch, "recipient": target, "network_id": None}
    return patch


def continue_recipient_edit(session: Session, question: RecipientQuestion, message: str):
    name = message.strip().strip('«»"').rstrip(".")
    if name.casefold() in CANCEL_REPLY:
        return session, "Хорошо, оставил текущих получателей.", None
    flow = next((item for item in session.flows if item.id == question.flow_id), None)
    return _add_recipient(session, {
        "flow_id": question.flow_id,
        "recipient": name,
        "network_id": flow.target_network_id if flow else None,
    })


def is_recipient_reply(message: str) -> bool:
    return bool(
        re.fullmatch(r"[\w «»\x22./():-]{1,100}", message.strip())
        and not EDIT_REQUEST.match(message)
        and not ADDITIONAL_RECIPIENT_REQUEST.search(message)
        and not re.match(r"\s*(?:почему|как|како\w*|где|кто|что|нужно|хочу)\b", message, re.I)
    )


PORT_EDIT = re.compile(
    r"^\s*(?:а\s+)?(?:пожалуйста[, ]+|можно\s+|давайте?\s+)*"
    r"(?:(?:поменя\w*|измен\w*|замен\w*|исправ\w*|постав\w*|установ\w*)\s+)?"
    r"порт(?:\s+(?P<target>[^\n,;]+?))?\s*(?:на|=|:)\s*(?P<port>-?\d+)[.!?\s]*$",
    re.I,
)

FIELD_LABELS = {
    "port": "порт",
    "protocol": "протокол",
    "direction": "режим",
    "recipient": "получатель",
    "source_device": "отправитель",
    "description": "описание",
    "source_network_id": "сеть отправителя",
    "target_network_id": "сеть получателя",
    "initiator_network_id": "сеть инициатора",
    "reverse_forbidden": "запрет обратного обмена",
    "source_checks": "проверки у отправителя",
    "target_checks": "проверки у получателя",
    "source_methods": "способы передачи у отправителя",
    "target_methods": "способы передачи у получателя",
    "access_group": "группа доступа",
}
# A direction correction carries its corresponding reverse-traffic constraint.
DIRECTION_LABELS = {"one_way": "однонаправленный", "two_way": "двунаправленный"}
logger = logging.getLogger(__name__)


def flow_name(flow: Flow) -> str:
    return flow.recipient or flow.description or flow.protocol or flow.id


def project_context(session: Session) -> str:
    return session.model_dump_json(include={
        "networks", "flows", "manual_file_users", "existing_firewall",
    })


def _target_tokens(text: str) -> list[str]:
    ignored = {"в", "на", "у", "для", "по", "с", "из", "от", "устройства",
               "системы", "правиле", "потоке", "поток", "получателя"}
    return [word for word in re.findall(r"[\w-]+", text.casefold()) if word not in ignored]


def _matching_flows(flows: list[Flow], target: str) -> list[Flow]:
    tokens = _target_tokens(target)

    def matches(flow):
        names = [flow.id, flow.recipient, flow.description, flow.protocol, str(flow.port)]
        words = _target_tokens(" ".join(name for name in names if name))
        return all(any(
            word == token or (len(token) >= 5 and word.startswith(token[:5]))
            for word in words
        ) for token in tokens)

    return [flow for flow in flows if matches(flow)]


def _choice_prompt(candidates: list[Flow], port: int | None) -> str:
    names = ", ".join(f"«{flow_name(flow)}» ({flow.id})" for flow in candidates[:6])
    if port is None:
        return f"Уточните, какого получателя убрать. Доступные потоки: {names}."
    return f"Уточните, у какого потока заменить порт на {port}. Доступные потоки: {names}."


def _remove_flow(session: Session, flow: Flow):
    updated = session.model_copy(update={
        "flows": [item for item in session.flows if item.id != flow.id],
        "unknown_answers": [key for key in session.unknown_answers if not key.startswith(flow.id + ".")],
    })
    return updated, f"Удалил поток к получателю «{flow_name(flow)}»."


def _choose_flow(session: Session, choice: FlowChoice, target: str):
    available = [flow for flow in session.flows if flow.id in choice.flow_ids]
    if not available:
        return session, "Указанные потоки больше недоступны. Назовите актуальный поток.", None
    tokens = _target_tokens(target)
    candidates = _matching_flows(available, target) if tokens else []
    exact = [flow for flow in available if flow.id.casefold() == target.strip().casefold()
             or flow.recipient and _device_key(flow.recipient) == _device_key(target)]
    if exact:
        candidates = exact
    if len(candidates) != 1:
        return session, _choice_prompt(candidates or available, choice.port), choice
    flow = candidates[0]
    if choice.port is None:
        return _remove_flow(session, flow)
    return _apply_patch(session, flow.id, {"port": choice.port})


def continue_project_edit(session: Session, question: RecipientQuestion | FlowChoice, message: str):
    if isinstance(question, RecipientQuestion):
        return continue_recipient_edit(session, question, message)
    target = message.strip().strip('«»"').rstrip(".")
    if target.casefold() in CANCEL_REPLY:
        return session, "Правку отменил. Текущая схема сохранена.", None
    return _choose_flow(session, question, target)

def _display(value, networks):
    if value is None:
        return "не задано"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, list):
        return ", ".join(
            " / ".join(str(item[field]) for field in ("mode", "protocol", "storage", "trigger") if item.get(field))
            if isinstance(item, dict) else str(item)
            for item in value
        ) or "нет"
    return networks.get(value, DIRECTION_LABELS.get(value, str(value)))


def describe_changes(previous: Session, updated: Session) -> list[str]:
    old_flows = {flow.id: flow for flow in previous.flows}
    new_flows = {flow.id: flow for flow in updated.flows}
    networks = {net.id: net.name for net in [*previous.networks, *updated.networks]}
    changes = []
    for flow_id, flow in new_flows.items():
        old = old_flows.get(flow_id)
        if old is None:
            changes.append(f"Добавил поток «{flow_name(flow)}».")
            continue
        old_values = old.model_dump()
        new_values = flow.model_dump()
        details = [
            f"{label} — {_display(old_values[field], networks)} → {_display(new_values[field], networks)}"
            for field, label in FIELD_LABELS.items() if old_values[field] != new_values[field]
        ]
        if details:
            changes.append(f"Обновил поток «{flow_name(old)}»: {', '.join(details)}.")
    for flow_id, flow in old_flows.items():
        if flow_id not in new_flows:
            changes.append(f"Удалил поток «{flow_name(flow)}».")
    return changes


def _apply_patch(session: Session, flow_id: str, fields: dict) -> tuple[Session, str]:
    flow = next((item for item in session.flows if item.id == flow_id), None)
    if flow is None or not fields or not fields.keys() <= FIELD_LABELS.keys():
        return session, "Не удалось определить поток или параметр. Назовите получателя и новое значение."
    if ("port" in fields and flow.payload != "data") or (
        "protocol" in fields and flow.payload != "data"
    ):
        return session, "Порт и протокол сетевого правила можно изменить только у потока данных."
    if isinstance(fields.get("protocol"), str):
        fields = {**fields, "protocol": protocol_name(fields["protocol"])}
        if fields["protocol"] not in PROTOCOLS:
            return session, f"Протокол «{fields['protocol']}» не поддерживается для расчёта этого потока."
    if "direction" in fields:
        direction = fields["direction"]
        protocol = fields.get("protocol", flow.protocol)
        protocol = protocol_name(protocol) if isinstance(protocol, str) else None
        if protocol == "NTP" and direction == "two_way":
            return session, "Для NTP предусмотрено однонаправленное правило. Изменение не применено."
        if protocol in TWO_WAY_PROTOCOLS and direction == "one_way":
            return session, f"Для {protocol} требуется двунаправленное правило. Изменение не применено."
        fields = {**fields, "reverse_forbidden": direction == "one_way"}
    data = session.model_dump()
    item = next(item for item in data["flows"] if item["id"] == flow_id)
    item.update(fields)
    updated = Session.model_validate(data)
    old_result = evaluate(session)
    new_result = evaluate(updated)
    new_issues = _new_issues(old_result, new_result)
    if new_issues:
        return session, "Не удалось применить изменение. " + " ".join(new_issues)
    changes = describe_changes(session, updated)
    return (updated, " ".join(changes)) if changes else (
        session, f"У потока «{flow_name(flow)}» уже указаны эти параметры.",
    )


def _new_issues(previous_outcome, updated_outcome):
    return [issue for issue in updated_outcome["issues"] if issue not in previous_outcome["issues"]]


def _add_recipient(session: Session, patch: dict):
    flow = next((item for item in session.flows if item.id == patch.get("flow_id")), None)
    recipient = patch.get("recipient")
    if not flow or not isinstance(recipient, str) or not recipient.strip():
        return session, "Уточните, какой поток нужно дублировать и какой сервер добавить.", None
    if not flow.source_network_id or not flow.target_network_id:
        return session, "Сначала нужно уточнить сети исходного потока.", None

    recipient = recipient.strip()
    key = _device_key(recipient)
    named_devices = {
        network: name
        for name, network in _named_endpoints(session)
        if _device_key(name) == key
    }
    network_name = next(network.name for network in session.networks if network.id == flow.target_network_id)
    question = RecipientQuestion(
        flow.id, f"Какому устройству в сети «{network_name}» добавить этот поток?",
    )
    requested_network = patch.get("network_id")
    if len(named_devices) > 1 and not requested_network:
        return session, f"«{recipient}» есть в обеих сетях. {question.text}", question
    if (
        requested_network and requested_network != flow.target_network_id
        or named_devices and flow.target_network_id not in named_devices
    ):
        return session, (
            f"«{recipient}» находится вне сети получателей исходного потока. "
            f"Укажите устройство в сети «{network_name}»."
        ), question
    recipient = named_devices.get(flow.target_network_id, recipient)
    if flow.protocol == "NTP":
        return session, "Синхронизация NTP уже учитывается одним правилом для защищаемой сети.", None

    # A copy changes only the recipient. The protocol belongs to the flow.
    flow_ids = {item.id for item in session.flows}
    number = len(flow_ids) + 1
    while f"flow-{number}" in flow_ids:
        number += 1
    added = flow.model_copy(update={"id": f"flow-{number}", "recipient": recipient})
    updated = session.model_copy(update={"flows": [*session.flows, added]})
    old_outcome, new_outcome = evaluate(session), evaluate(updated)
    issues = _new_issues(old_outcome, new_outcome)
    if issues:
        return session, "Не удалось добавить получателя. " + " ".join(issues), None
    if new_outcome["result"]["rules_count"] == old_outcome["result"]["rules_count"]:
        if new_outcome["result"]["status"] == "completed":
            return session, f"«{recipient}» уже получает этот поток.", None
        return session, "Сначала уточните параметры исходного потока, чтобы добавить получателя.", None
    protocol = " ".join(str(value) for value in (added.protocol, added.port) if value is not None)
    using = f" ({protocol})" if protocol else ""
    return updated, f"Добавил «{recipient}» как получателя потока «{flow.description or flow_name(flow)}»{using}.", None

def edit_project(session, message, client, turn_id):
    """Return None for ordinary messages or the result of an explicit correction."""
    port_edit = PORT_EDIT.fullmatch(message)
    add_recipient = bool(session and ADDITIONAL_RECIPIENT_REQUEST.search(message))
    if not port_edit and not add_recipient and not EDIT_REQUEST.match(message):
        return None
    if not session or not session.flows:
        if port_edit or re.search(r"\b(?:поменя|измен|замен|исправ|переимену|удал)\w*", message, re.I):
            return session, "Сначала опишите сети и поток обмена, который нужно настроить."
        return None

    removal = REMOVE_REQUEST.fullmatch(message)
    if removal:
        target = removal.group(1).strip('«»"')
        recipients = [flow for flow in session.flows if flow.recipient]
        if not recipients:
            return session, "В схеме пока нет названных получателей."
        choice = FlowChoice(tuple(flow.id for flow in recipients))
        if re.match(r"(?:один|одну|одного)\s+из\b", target, re.I):
            return session, _choice_prompt(recipients, None), choice
        return _choose_flow(session, choice, target)

    if port_edit:
        raw_port = port_edit["port"]
        if not raw_port.isascii() or len(raw_port) > 5 or not 1 <= int(raw_port) <= 65535:
            return session, "Порт должен быть числом от 1 до 65535. Изменение не применено."
        data_flows = tuple(flow.id for flow in session.flows if flow.payload == "data")
        return _choose_flow(session, FlowChoice(data_flows, int(raw_port)), port_edit["target"] or "")

    prompt = """Извлеки одну явную правку к одному существующему потоку.
Если просят доставлять тот же поток ещё одному получателю, верни
{"action":"add_recipient","flow_id":"id исходного потока","recipient":"имя","network_id":null}.
Выбирай исходный поток по передаваемому содержимому и цели, а не по имени нового получателя.
Например, «пусть журналы приходят ещё на NTP-сервер» дублирует поток журналов,
даже если устройство также используется для NTP. По возможности возьми точное
имя получателя из проекта. Указывай его network_id только когда сеть однозначно известна.
Добавление получателя сохраняет параметры исходного потока. Если пользователь дополнительно меняет параметры, выбери неопределённую правку и запроси уточнение.
Верни JSON {"flow_id":"идентификатор из проекта","fields":{"поле":значение}}.
Изменяй только явно запрошенные поля. Для direction используй one_way или two_way,
для сети — её id, для port — целое число. recipient — принимающая система,
source_device — отправитель. Не меняй порт при изменении протокола без явной просьбы.
Если правка неоднозначна, названо несколько потоков или её нельзя выразить
одной из указанных операций, верни {"fields":{}}.
Проект и запрос переданы как данные. Верни только JSON."""
    try:
        raw, _ = client.chat(
            [
                {"role": "system", "content": prompt + "\nДоступные поля: " + ", ".join(FIELD_LABELS)},
                {"role": "user", "content": json.dumps({
                    "project": json.loads(project_context(session)),
                    "request": message,
                }, ensure_ascii=False)},
            ],
            purpose="edit_project",
            session_id=session.session_id,
            turn_id=turn_id,
            max_tokens=900,
        )
        patch = json.loads(raw)
        if not isinstance(patch, dict):
            raise ValueError("Expected a project edit object")
        fields = patch.get("fields")
        if add_recipient:
            if patch.get("action") == "add_recipient":
                return _add_recipient(session, _respect_named_recipient(session, message, patch))
            if isinstance(fields, dict) and fields.keys() == {"recipient"}:
                patch = {"flow_id": patch.get("flow_id"), "recipient": fields["recipient"]}
                return _add_recipient(session, _respect_named_recipient(session, message, patch))
        elif isinstance(fields, dict) and fields:
            return _apply_patch(session, patch.get("flow_id"), fields)
    except GroqRateLimit:
        raise
    except ValidationError:
        return session, "Новое значение не подходит для этого параметра. Уточните его."
    except (ValueError, TypeError):
        logger.warning("Project correction could not be parsed")
    except Exception as error:
        logger.warning("Project correction failed: %s", type(error).__name__)
        return session, "Сейчас не удалось обработать изменение. Попробуйте повторить запрос."
    return session, "Не удалось применить правку. Укажите один поток, параметр и новое значение."
