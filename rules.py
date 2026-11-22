"""Deterministic project design for Synonyx 1.9. No network or LLM calls."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RULE_LIMIT = 256
TWO_WAY_PROTOCOLS = {"MQTT", "Modbus TCP", "МЭК 104"}
PROTOCOLS = ("TCP", "UDP", "NTP", "MQTT", "Modbus TCP", "МЭК 104")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Network(Model):
    id: str
    name: str
    kind: Literal["open", "closed"] | None = None


class FileMethod(Model):
    mode: Literal["manual", "USB", "PULL", "PUSH"]
    protocol: str | None = None
    storage: str | None = None
    trigger: Literal["arrival", "schedule"] | None = None


class Flow(Model):
    id: str
    description: str | None = None
    source_network_id: str | None = None
    target_network_id: str | None = None
    payload: Literal["data", "files"] | None = None
    direction: Literal["one_way", "two_way"] | None = None
    reverse_forbidden: bool | None = None
    initiator_network_id: str | None = None
    recipient: str | None = None
    source_device: str | None = None
    protocol: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    source_methods: list[FileMethod] | None = None
    target_methods: list[FileMethod] | None = None
    source_checks: list[str] | None = None
    target_checks: list[str] | None = None
    access_group: str | None = None
    separate_file_access: bool = False


class Session(Model):
    session_id: str
    networks: list[Network] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)
    assumptions: dict[str, str] = Field(default_factory=dict)
    unknown_answers: list[str] = Field(default_factory=list)
    requests_for_vendor: list[str] = Field(default_factory=list)
    manual_file_users: list[str] | None = None
    manual_users_count: int | None = Field(default=None, ge=0)
    existing_firewall: str | None = None
    devices: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    usage: dict = Field(default_factory=lambda: {
        "status": "not_measured", "input_tokens": None, "output_tokens": None,
        "input_cost_usd": None, "output_cost_usd": None, "evaluation_cost_usd": None,
        "actual_cost_usd": None, "calls": [],
    })
    timing: dict = Field(default_factory=lambda: {"turns": [], "mean_turn_seconds": None})

    @model_validator(mode="after")
    def validate_ids(self):
        networks = {network.id for network in self.networks}
        if len(networks) != len(self.networks):
            raise ValueError("Идентификаторы сетей должны быть уникальны.")
        if len({flow.id for flow in self.flows}) != len(self.flows):
            raise ValueError("Идентификаторы потоков должны быть уникальны.")
        for flow in self.flows:
            refs = (flow.source_network_id, flow.target_network_id, flow.initiator_network_id)
            if any(ref is not None and ref not in networks for ref in refs):
                raise ValueError(f"Поток {flow.id} ссылается на неизвестную сеть.")
        if self.assumptions.get("same_file_checks") == "yes":
            self._reuse_common_file_checks()
        return self

    def _reuse_common_file_checks(self):
        checks_by_network = defaultdict(set)
        sides = (("source_network_id", "source_checks"), ("target_network_id", "target_checks"))
        files = [flow for flow in self.flows if flow.payload == "files"]
        for flow in files:
            for endpoint, field in sides:
                network, checks = getattr(flow, endpoint), getattr(flow, field)
                if network is not None and checks is not None:
                    checks_by_network[network].add(tuple(sorted(set(checks))))
        for index, flow in enumerate(self.flows):
            if flow.payload != "files":
                continue
            inherited = {}
            for endpoint, field in sides:
                profiles = checks_by_network.get(getattr(flow, endpoint), ())
                if len(profiles) == 1 and getattr(flow, field) is None:
                    inherited[field] = list(next(iter(profiles)))
            if inherited:
                self.flows[index] = flow.model_copy(update=inherited)


QUESTIONS = {
    "payload": ("Что нужно передавать?", ("Резервные копии", "Журналы", "Телеметрия", "Время", "Файлы")),
    "direction": ("Нужна ли передача в обратную сторону?", ("Нет, только в одну сторону", "Да, нужен ответ или обмен")),
    "source_network_id": ("Из какой сети идёт поток?", ()),
    "target_network_id": ("В какую сеть идёт поток?", ()),
    "initiator_network_id": ("Какая сеть инициирует соединение?", ()),
    "recipient": ("Какие системы принимают данные? Укажите имя или назначение каждой. "
                  "Если систем несколько, разделите их точкой с запятой.", ()),
    "source_device": ("Какая система на противоположной от инициатора стороне принимает соединение?", ()),
    "protocol": ("Какой протокол используется?", PROTOCOLS),
    "port": ("Какой порт принимает соединение?", ()),
    "source_methods": ("Как отправляются файлы?", ("Вручную по SFTP", "USB", "PULL")),
    "target_methods": ("Куда должны попасть файлы?", ("Заберёт человек вручную", "Автоматически в хранилище", "На флешку")),
    "source_checks": ("Какие проверки и наборы нужны у отправителя?", (
        "Без проверок", "Маска имени", "Тип и расширение", "Размер", "Целостность", "Проверка по ICAP")),
    "target_checks": ("Какие проверки и наборы нужны у получателя?", (
        "Без проверок", "Маска имени", "Тип и расширение", "Размер", "Целостность", "Проверка по ICAP")),
    "access_group": ("Могут ли пользователи видеть принятые файлы друг друга?", ("Да", "Нет")),
}


def protocol_name(protocol):
    aliases = {name.casefold(): name for name in PROTOCOLS}
    aliases.update({"modbus": "Modbus TCP", "мэк-104": "МЭК 104", "iec 104": "МЭК 104"})
    return aliases.get(protocol.strip().casefold(), protocol.strip())


def file_method_issue(method, *, sending, from_open):
    if method.mode == "USB":
        if not from_open:
            return "USB подключается только к Узлу А со стороны открытой сети."
        return None
    if method.mode == "manual":
        if method.protocol not in (None, "SFTP"):
            return "Ручная передача файлов выполняется по SFTP."
        return None
    if (method.mode == "PULL") != sending:
        return "PULL настраивается на отправляющей стороне, PUSH — на принимающей."
    if method.protocol not in (None, "SFTP", "FTP", "SMB"):
        return "Для автоматической передачи файлов доступны SFTP, FTP и SMB."
    return None


def file_candidates(flow):
    source_methods = list({tuple(m.model_dump().items()): m for m in flow.source_methods}.values())
    target_methods = list({tuple(m.model_dump().items()): m for m in flow.target_methods}.values())
    # Automatic settings are bound to a single rule.
    pull = [m for m in source_methods if m.mode == "PULL"]
    push = [m for m in target_methods if m.mode == "PUSH"]
    source_manual = [m for m in source_methods if m.mode != "PULL"]
    target_manual = [m for m in target_methods if m.mode != "PUSH"]
    if len(pull) > 1 and len(push) > 1:
        raise ValueError("Уточните, какие хранилища PULL связаны с какими хранилищами PUSH.")
    return [
        (
            source_manual + (pull if len(pull) == 1 else pull[index:index + 1]),
            target_manual + (push if len(push) == 1 else push[index:index + 1]),
        )
        for index in range(max(1, len(pull), len(push)))
    ]


def flow_may_use_manual_transfer(flow):
    return flow.payload == "files" and (
        not flow.source_methods or not flow.target_methods
        or any(method.mode in ("manual", "USB") for method in flow.source_methods + flow.target_methods)
    )


def file_method_label(method):
    if method.mode == "USB":
        return "USB-носитель на Узле А"
    if method.mode == "manual":
        return "SFTP, вручную"
    if method.mode == "PULL":
        return f"{method.protocol}, автоматический забор"
    if method.trigger == "arrival":
        return f"{method.protocol}, автоматически при поступлении"
    return f"{method.protocol}, автоматически"


def evaluate(session: Session) -> dict:
    questions = {}
    issues = []
    rules = []
    rule_details = []
    data_groups = {}
    file_groups = defaultdict(list)
    file_automation_by_network = defaultdict(set)
    network_options = tuple(network.name for network in session.networks)

    def ask(key, label, options=()):
        questions[key] = {"id": key, "text": label, "options": [*options, "Не знаю", "Другое"]}

    def missing(flow, field):
        label, options = QUESTIONS[field]
        if field == "source_network_id":
            options = tuple(n.name for n in session.networks if n.id != flow.target_network_id)
        elif field == "target_network_id":
            options = tuple(n.name for n in session.networks if n.id != flow.source_network_id)
        elif field == "initiator_network_id":
            options = tuple(n.name for n in session.networks if n.id in (
                flow.source_network_id, flow.target_network_id
            ))
        elif synonyx and field == "source_methods" and flow.source_network_id != synonyx["node_a"]:
            options = tuple(option for option in options if option != "USB")
        elif synonyx and field == "target_methods" and flow.target_network_id != synonyx["node_a"]:
            options = tuple(option for option in options if option != "На флешку")
        ask(f"{flow.id}.{field}", f"Поток {flow.id}. {label}", options)

    closed = [n.id for n in session.networks if n.kind == "closed"]
    opened = [n.id for n in session.networks if n.kind == "open"]
    firewall = synonyx = None
    if len(session.networks) > 2:
        issues.append("Проект поддерживает одну пару сетей.")
    elif len(session.networks) == 1:
        known = session.networks[0]
        options = {"closed": ("Открытая сеть",), "open": ("Закрытая сеть",)}.get(known.kind, ())
        other_side = "Какая сеть находится на другой стороне обмена?"
        if any(flow.target_network_id == known.id for flow in session.flows):
            other_side = f"Из какой сети нужно передавать файлы или данные в «{known.name}»?"
        elif any(flow.source_network_id == known.id for flow in session.flows):
            other_side = f"В какую сеть нужно передавать файлы или данные из «{known.name}»?"
        ask("networks", other_side, options)
    elif not session.networks:
        ask("networks", "Какие две сети должны обмениваться информацией?")
    else:
        protected = closed[0] if len(closed) == 1 else session.assumptions.get("protected_network_id")
        ids = {n.id for n in session.networks}
        if protected not in ids:
            ask("protected_network_id", "Какую сеть защищаем в этом проекте?", network_options)
        else:
            external = next(n.id for n in session.networks if n.id != protected)
            if len(opened) == 2 and "protected_network_id" not in session.assumptions:
                ask("protected_network_id", "Какую из двух открытых сетей защищаем?", network_options)
            else:
                firewall = {"network": protected, "side": external, "existing": session.existing_firewall}
                synonyx = {"network": protected, "node_a": external, "core": protected, "node_b": protected}

    if not session.flows and not issues:
        ask("flows", "Какие данные или файлы нужно передавать между сетями?")

    for flow in session.flows:
        before = len(questions)
        missing_endpoints = flow.source_network_id is None or flow.target_network_id is None
        if len(session.networks) < 2 and missing_endpoints:
            continue
        for field in ("source_network_id", "target_network_id", "payload"):
            if getattr(flow, field) is None:
                missing(flow, field)
        if len(questions) != before:
            continue

        source, target = flow.source_network_id, flow.target_network_id
        if source == target:
            issues.append(f"Поток {flow.id} должен пересекать границу двух сетей.")
            continue

        if flow.payload == "data":
            if flow.protocol is None:
                missing(flow, "protocol")
                continue
            protocol = protocol_name(flow.protocol)
            if protocol not in PROTOCOLS:
                issues.append(f"Поток {flow.id}: протокол {protocol} вне поддерживаемых режимов расчёта.")
                continue
            if protocol == "NTP":
                if synonyx and target != synonyx["node_b"]:
                    issues.append(f"Поток {flow.id}: NTP направляется в защищаемую сеть.")
                    continue
                mode = "one_way"
                recipient = None
            else:
                mode = "two_way" if protocol in TWO_WAY_PROTOCOLS else flow.direction
                if mode is None and flow.reverse_forbidden:
                    mode = "one_way"
                if mode is None:
                    missing(flow, "direction")
                    continue
                if mode == "two_way" and flow.reverse_forbidden:
                    issues.append(f"Поток {flow.id}: двунаправленный режим конфликтует с запретом обратного обмена.")
                    continue
                recipient = flow.recipient
                recipient_field = "recipient"
                if mode == "two_way":
                    if flow.initiator_network_id not in (source, target):
                        missing(flow, "initiator_network_id")
                        continue
                    elif flow.initiator_network_id == target:
                        source, target = target, source
                        recipient = flow.source_device
                        recipient_field = "source_device"
                if not recipient or not recipient.strip():
                    missing(flow, recipient_field)
                    if f"{flow.id}.{recipient_field}" not in session.unknown_answers:
                        continue
            if flow.port is None and protocol != "NTP":
                missing(flow, "port")
                if f"{flow.id}.port" not in session.unknown_answers:
                    continue
            if protocol != "NTP" and (not recipient or not recipient.strip()):
                continue
            port_key = (
                None if protocol == "NTP" else flow.port if flow.port is not None else flow.id
            )
            recipient_key = recipient.strip().casefold() if recipient else None
            key = (source, target, mode, protocol, port_key, recipient_key)
            if key in data_groups:
                if protocol == "NTP" and flow.port is not None:
                    previous = data_groups[key]
                    if previous["port"] is not None and previous["port"] != flow.port:
                        issues.append("Для NTP указаны противоречащие друг другу порты.")
                    else:
                        previous["port"] = flow.port
                continue
            rule = {"type": "data", "from": source, "to": target, "mode": mode.replace("_", "-"),
                    "protocol": "UDP" if protocol == "NTP" else protocol,
                    "description": flow.description or "Отправители используют collect, конечный получатель — exchange."}
            rule["port"] = flow.port
            data_groups[key] = rule
            rules.append(rule)
            endpoint_names = {flow.source_network_id: flow.source_device, flow.target_network_id: flow.recipient}
            rule_details.append({"recipient": flow.recipient, "application_protocol": protocol,
                                 "from_device_name": endpoint_names[source], "to_device_name": endpoint_names[target]})
            continue

        if flow.direction == "two_way" and flow.reverse_forbidden:
            issues.append(f"Поток {flow.id}: запрошены оба направления и одновременно запрещена обратная передача.")
            continue
        if any(method.mode == "PULL" for method in flow.source_methods or []):
            file_automation_by_network[source].add("PULL")
        if any(method.mode == "PUSH" for method in flow.target_methods or []):
            file_automation_by_network[target].add("PUSH")
        for field in ("direction", "source_methods", "target_methods", "access_group"):
            if not getattr(flow, field):
                if field == "access_group" and flow.separate_file_access:
                    ask(f"{flow.id}.access_groups",
                        "Назовите группы, которые должны получать файлы отдельно. Перечислите через запятую.")
                else:
                    missing(flow, field)
        missing_transfer = not flow.direction or not flow.source_methods or not flow.target_methods
        missing_checks = [field for field in ("source_checks", "target_checks") if getattr(flow, field) is None]
        same_checks = session.assumptions.get("same_file_checks") == "yes"
        for field in missing_checks:
            if same_checks:
                network_id = source if field == "source_checks" else target
                name = next((network.name for network in session.networks if network.id == network_id), network_id)
                ask(f"file_checks:{network_id}", f"Какие общие проверки файлов нужны на стороне «{name}»?",
                    QUESTIONS[field][1])
            else:
                missing(flow, field)
        if missing_transfer:
            continue
        before = len(questions)
        if flow.direction == "two_way":
            ask(f"{flow.id}.file_directions", "Укажите способы и проверки отдельно для каждого направления файлового обмена.")
            continue
        if any("встроенн" in check.casefold() and "антивирус" in check.casefold()
               for check in (flow.source_checks or []) + (flow.target_checks or [])):
            issues.append("Встроенного антивируса нет. Можно согласовать внешнюю проверку по ICAP.")
            continue

        invalid = []
        for sending, methods in ((True, flow.source_methods), (False, flow.target_methods)):
            method_field = "source_methods" if sending else "target_methods"
            for index, method in enumerate(methods):
                if method.mode == "USB" and synonyx is None:
                    ask("protected_network_id", "Какая сеть защищаемая для проверки подключения USB?", network_options)
                    continue
                method_network = source if sending else target
                issue = file_method_issue(method, sending=sending, from_open=bool(synonyx and method_network == synonyx["node_a"]))
                if issue:
                    invalid.append(issue)
                if method.mode in ("PULL", "PUSH"):
                    if method.protocol is None:
                        ask(f"{flow.id}.{method_field}.{index}.protocol", "Какой протокол использует хранилище?", ("SFTP", "FTP", "SMB"))
                    if not method.storage:
                        ask(f"{flow.id}.{method_field}.{index}.storage", "Какое хранилище использует эта настройка?")
        if invalid:
            issues.extend(invalid)
            continue
        if len(questions) != before or not flow.access_group or (missing_checks and not same_checks):
            continue
        try:
            candidates = file_candidates(flow)
        except ValueError as error:
            ask(f"{flow.id}.storage_mapping", str(error) + " Запишите каждую пару через →, а пары разделите точкой с запятой.")
            continue
        checks = {source: tuple(sorted(set(flow.source_checks or []))), target: tuple(sorted(set(flow.target_checks or [])))}
        profile = tuple(sorted(checks.items()))
        for left, right in candidates:
            entry = (source, target, left, right, flow.access_group, flow)
            group = file_groups[profile]
            for index, (a, b, send, receive, access, original) in enumerate(group):
                if (source, target, flow.access_group) != (a, b, access):
                    continue
                existing = [m for m in send + receive if m.mode in ("PULL", "PUSH")]
                incoming = [m for m in left + right if m.mode in ("PULL", "PUSH")]
                if existing and incoming and existing != incoming:
                    continue
                group[index] = (a, b, send + [m for m in left if m not in send],
                                receive + [m for m in right if m not in receive], access, original)
                break
            else:
                group.append(entry)

    pull_rules = 0
    for profile, entries in file_groups.items():
        # Each directed entry can pair with an opposite entry if it does not
        # require a second PULL or another automatic setting on either node.
        def automation(methods):
            return {m.mode for m in methods if m.mode in ("PULL", "PUSH")}

        def compatible(left, right):
            a, b, send, receive, access, forward_flow = left
            c, d, reverse_send, reverse_receive, reverse_access, reverse_flow = right
            if forward_flow.reverse_forbidden or reverse_flow.reverse_forbidden:
                return False
            if (a, b, access) != (d, c, reverse_access):
                return False
            return not (
                automation(send) and automation(reverse_receive)
                or automation(receive) and automation(reverse_send)
                or "PULL" in automation(send) and "PULL" in automation(reverse_send)
            )

        first_network = min(network for network, _ in profile)
        forward = [i for i, entry in enumerate(entries) if entry[0] == first_network]
        backward = [i for i, entry in enumerate(entries) if entry[0] != first_network]
        matching = {}

        def pair(index, seen):
            for other in backward:
                if other in seen or not compatible(entries[index], entries[other]):
                    continue
                seen.add(other)
                if other not in matching or pair(matching[other], seen):
                    matching[other] = index
                    return True
            return False

        for index in forward:
            pair(index, set())
        partners = {min(i, j): max(i, j) for i, j in matching.items()}
        skipped = set(partners.values())
        for index, (source, target, send, receive, access, flow) in enumerate(entries):
            if index in skipped:
                continue
            mode = "one_way"
            if index in partners:
                _, _, reverse_send, reverse_receive, _, _ = entries[partners[index]]
                send = send + reverse_receive
                receive = receive + reverse_send
                mode = "two_way"
            pull_rules += any(m.mode == "PULL" for m in send + receive)
            protocols = {network: "; ".join(dict.fromkeys(file_method_label(m) for m in methods))
                         for network, methods in ((source, send), (target, receive))}
            checks = list(dict.fromkeys((flow.source_checks or []) + (flow.target_checks or [])))
            rule = {"type": "file", "from": source, "to": target, "mode": mode.replace("_", "-"),
                    "protocol": protocols, "checks": checks,
                    "description": flow.description or "Общий профиль проверок и доступа."}
            rules.append(rule)
            rule_details.append({"methods": {
                              source: [m.model_dump(exclude_none=True) for m in send],
                              target: [m.model_dump(exclude_none=True) for m in receive],
                          }, "access_group": access, "checks_by_node": {
                              network: values for network, values in profile
                              if (flow.source_checks if network == source else flow.target_checks) is not None
                          },
                             "from_device_name": flow.source_device, "to_device_name": flow.recipient})

    if len(rules) > RULE_LIMIT:
        issues.append(f"Требуется {len(rules)} правил при лимите {RULE_LIMIT} на один ПАК.")
    for index, rule in enumerate(rules, 1):
        rule["id"] = index

    manual_transfer_possible = any(flow_may_use_manual_transfer(flow) for flow in session.flows)
    if synonyx and manual_transfer_possible and session.manual_file_users is None and session.manual_users_count is None:
        ask("manual_users_count", "Сколько разных людей будут вручную передавать или получать файлы?")
    unanswered = [key for key in questions if key not in session.unknown_answers]
    unconfigured_files = any(
        flow.payload == "files" and flow.source_network_id and flow.target_network_id
        and any(key.startswith(flow.id + ".") for key in questions)
        for flow in session.flows
    )
    minimum = len(rules)
    minimum_reason = ""
    pull_networks = sum("PULL" in modes for modes in file_automation_by_network.values())
    if unconfigured_files:
        common_node = next((key for key, modes in file_automation_by_network.items() if len(modes) > 1), None)
        file_minimum = 2 if common_node or pull_networks > 1 else 1
        counted_files = sum(rule["type"] == "file" for rule in rules)
        minimum += max(0, file_minimum - counted_files)
        if file_minimum > counted_files and common_node:
            name = next(network.name for network in session.networks if network.id == common_node)
            minimum_reason = (
                f"На стороне «{name}» нужны и автоматический забор (PULL), и доставка (PUSH). "
                "В одном правиле для этой стороны можно задать только одну автоматическую настройку."
            )
        elif file_minimum > counted_files and pull_networks > 1:
            minimum_reason = "Забор файлов нужен с обеих сторон. На каждую сторону с PULL требуется отдельное правило."
    if issues:
        status = "unsupported"
    elif not synonyx:
        status = "preliminary" if "protected_network_id" in session.unknown_answers else "needs_clarification"
    elif questions:
        status = "preliminary" if rules or minimum and not unanswered else "needs_clarification"
    else:
        status = "completed"

    has_files = any(flow.payload == "files" for flow in session.flows)
    known_people = {name.strip().casefold() for name in session.manual_file_users or [] if name.strip()}
    manual_count = 0
    if manual_transfer_possible:
        manual_count = session.manual_users_count if session.manual_users_count is not None else len(known_people)
    file_users_unknown = has_files and ("manual_users_count" in questions or unconfigured_files)
    result = {
        "schema_version": "1.1", "session_id": session.session_id, "status": status,
        "networks": [{"id": n.id, "name": n.name, "trust": n.kind} for n in session.networks],
        "firewall": {"side": "open"} if firewall else None,
        "synonyx": {"location": synonyx["network"], "node_a_faces": synonyx["node_a"],
                    "node_b_faces": synonyx["node_b"]} if synonyx else None,
        "rules": rules, "rules_count": len(rules),
        "file_users_count": None if file_users_unknown else manual_count + pull_rules if has_files else 0,
        "requests_for_vendor": list(dict.fromkeys([*session.requests_for_vendor, *issues])),
        "unknowns": list(questions), "assumptions": [
            {"id": key, "value": value} for key, value in session.assumptions.items()
        ], "devices": session.devices,
        "sources": session.sources, "usage": session.usage, "timing": session.timing,
        "file_users_range": None,
    }
    if file_users_unknown:
        result["file_users_range"] = {"min": manual_count + pull_rules, "max": None}
    return {"result": result, "questions": [questions[key] for key in unanswered], "issues": issues,
            "deferred_questions": [question for key, question in questions.items() if key not in unanswered],
            "minimum_rules_count": minimum,
            "minimum_rules_reason": minimum_reason,
            "existing_firewall": session.existing_firewall,
            "rule_details": {rule["id"]: detail for rule, detail in zip(rules, rule_details)}}


def record_unresolved_answer(session: Session, question_id: str, other: str | None = None) -> Session:
    """Record 'Не знаю' or preserve a 'Другое' answer for expert review."""
    if question_id not in evaluate(session)["result"]["unknowns"]:
        raise ValueError("Вопрос больше не относится к текущему состоянию.")
    if other is not None and not other.strip():
        raise ValueError("Укажите текст ответа «Другое».")
    unknowns = list(dict.fromkeys([*session.unknown_answers, question_id]))
    requests = session.requests_for_vendor.copy()
    if other is not None:
        requests = list(dict.fromkeys([*requests, f"{question_id}: {other.strip()}"]))
    return session.model_copy(update={"unknown_answers": unknowns, "requests_for_vendor": requests})


def _split_flow(data, flow, variants, suffix, answered_key):
    flow_id = flow["id"]
    ids = {item["id"] for item in data["flows"]}
    deferred = [key for key in data["unknown_answers"]
                if key.startswith(flow_id + ".") and key != answered_key]
    for position, variant in enumerate(variants, 1):
        if position == 1:
            flow.update(variant)
            continue
        index = position
        new_id = f"{flow_id}-{suffix}-{index}"
        while new_id in ids:
            index += 1
            new_id = f"{flow_id}-{suffix}-{index}"
        ids.add(new_id)
        data["flows"].append({**flow, **variant, "id": new_id})
        data["unknown_answers"].extend(new_id + key[len(flow_id):] for key in deferred)


def _apply_storage_mapping(data, flow, pairs, question_id):
    def by_storage(field, mode):
        methods = [method for method in flow[field] if method["mode"] == mode]
        named = {method["storage"].strip().casefold(): method for method in methods}
        if len(named) != len(methods):
            raise ValueError("В конфигурации есть одинаковые имена хранилищ. Уточните, какие настройки входят в каждый поток.")
        return named

    pull = by_storage("source_methods", "PULL")
    push = by_storage("target_methods", "PUSH")
    selected = list(dict.fromkeys((left.strip().casefold(), right.strip().casefold()) for left, right in pairs))
    if {left for left, _ in selected} != set(pull) or {right for _, right in selected} != set(push):
        raise ValueError("Назовите все указанные хранилища по одному или нескольким маршрутам, без новых имён.")
    source_manual = [method for method in flow["source_methods"] if method["mode"] != "PULL"]
    target_manual = [method for method in flow["target_methods"] if method["mode"] != "PUSH"]
    variants = [
        {"source_methods": [*source_manual, pull[left]], "target_methods": [*target_manual, push[right]]}
        for left, right in selected
    ]
    _split_flow(data, flow, variants, "route", question_id)


def apply_answer(session: Session, question_id: str, value) -> Session:
    """Apply a confirmed structured answer to a new, validated session snapshot."""
    if question_id not in evaluate(session)["result"]["unknowns"]:
        raise ValueError("Вопрос больше не относится к текущему состоянию.")
    data = session.model_dump()
    if question_id == "protected_network_id":
        if value not in {network.id for network in session.networks}:
            raise ValueError("Выберите идентификатор одной из указанных сетей.")
        data["assumptions"][question_id] = value
    elif question_id == "manual_users_count":
        data[question_id] = value
    elif question_id == "networks":
        data["networks"] = value
        if len(session.networks) == 1 and len(value) == 2:
            known_id = session.networks[0].id
            other_id = next(network["id"] for network in value if network["id"] != known_id)
            for flow in data["flows"]:
                if flow["source_network_id"] is None and flow["target_network_id"] == known_id:
                    flow["source_network_id"] = other_id
                elif flow["target_network_id"] is None and flow["source_network_id"] == known_id:
                    flow["target_network_id"] = other_id
    elif question_id == "flows":
        data["flows"] = value
    elif question_id.startswith("file_checks:"):
        network_id = question_id.partition(":")[2]
        for flow in data["flows"]:
            if flow["payload"] != "files":
                continue
            for endpoint, field in (("source_network_id", "source_checks"), ("target_network_id", "target_checks")):
                if flow[endpoint] == network_id and flow[field] is None:
                    flow[field] = value
    else:
        flow = max((f for f in data["flows"] if question_id.startswith(f["id"] + ".")),
                   key=lambda f: len(f["id"]), default=None)
        if flow is None:
            raise ValueError("Для этого уточнения требуется обновить описание потока.")
        path = question_id[len(flow["id"]) + 1:].split(".")
        if path == ["access_group"] and value is False:
            flow["separate_file_access"] = True
        elif path == ["access_groups"]:
            _split_flow(data, flow, [{"access_group": group} for group in value], "group", question_id)
        elif path in (["recipient"], ["source_device"]) and isinstance(value, list):
            _split_flow(data, flow, [{path[0]: name} for name in value], "recipient", question_id)
        elif path == ["storage_mapping"]:
            _apply_storage_mapping(data, flow, value, question_id)
        elif len(path) == 1 and path[0] in QUESTIONS:
            flow[path[0]] = value
            if path == ["direction"]:
                flow["reverse_forbidden"] = value == "one_way"
        elif len(path) == 3 and path[0] in ("source_methods", "target_methods"):
            field, index, attr = path
            flow[field][int(index)][attr] = value
        else:
            raise ValueError("Для этого уточнения требуется обновить описание потока.")
    data["unknown_answers"] = [key for key in data["unknown_answers"] if key != question_id]
    return Session.model_validate(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="Входной JSON состояния сессии")
    parser.add_argument("--with-questions", action="store_true")
    args = parser.parse_args()
    session = Session.model_validate_json(args.session.read_text(encoding="utf-8-sig"))
    outcome = evaluate(session)
    print(json.dumps(outcome if args.with_questions else outcome["result"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
