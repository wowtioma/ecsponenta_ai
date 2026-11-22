"""Извлечение слотов из свободного текста (участок B).

Основной путь — один дешёвый LLM-вызов (client.chat с SYSTEM_EXTRACT), ответ
парсится как JSON. Есть и быстрый regex-фолбэк quick_extract() для офлайн-тестов
и как бесплатная первая оценка (экономия токенов).

Результат извлечения — обычный dict, который участник A кладёт в своё внутреннее
представление сессии (см. result.example.json). Мы НЕ считаем правила здесь — это
задача A (core/rules.py).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import prompts
from .client import GroqRateLimit, LLMClient

logger = logging.getLogger("llm.extract")

# --- regex-фолбэк ---------------------------------------------------------

_PROTOCOL_PATTERNS: list[tuple[str, str]] = [
    ("Modbus TCP", r"modbus\s*tcp"),
    ("МЭК 104", r"мэк\s*(?:60870[- ]?5[- ]?)?104"),
    ("MQTT", r"\bmqtt\b"),
    ("NTP", r"\bntp\b"),
    ("SFTP", r"\bsftp\b"),
    ("SMB", r"\bsmb\b"),
    ("FTP", r"(?<![a-z])ftp\b"),
    ("UDP", r"\budp\b"),
    ("TCP", r"\btcp\b"),
]

_PORT_RE = re.compile(r"(?:порт(?:а|у|е)?|:)\s*(\d{1,5})")

_FILE_WORDS = {"файл", "файлов", "файлы", "обновлени", "флешк", "usb", "sftp", "smb", "ftp"}
_DATA_WORDS = {"журнал", "телеметр", "время", "ntp", "modbus", "mqtt", "мэк", "опрос",
               "данны", "syslog", "резерв", "показан"}
_CLOSED_WORDS = {"закрыт", "цех", "сегмент", "станц", "асутп", "контур", "защища"}
_OPEN_WORDS = {"офис", "открыт", "общ", "интернет", "диспетчер"}


def _lower(text: str) -> str:
    return text.lower()


def _has_any(low: str, words: set[str]) -> bool:
    return any(w in low for w in words)


def quick_extract(text: str) -> dict[str, Any]:
    """Быстрое regex-извлечение без LLM. Только для тестов и бесплатной оценки.

    Возвращает {"networks", "flows", "unknowns", "assumptions"}. Направление и
    режим в фолбэке не определяются — помечаются unknown.
    """
    low = _lower(text)
    protocols = [name for name, pat in _PROTOCOL_PATTERNS if re.search(pat, low)]

    flows: list[dict] = []
    for proto in protocols:
        port = None
        m = _PORT_RE.search(low)
        if m:
            port = int(m.group(1))
        ftype = "file" if _has_any(low, _FILE_WORDS) and proto in ("SFTP", "SMB", "FTP") else "data"
        flows.append(
            {
                "type": ftype,
                "from": None,
                "to": None,
                "mode": "unknown",
                "protocol": proto,
                "port": port,
                "description": "",
                "checks": [],
                "method_open": None,
                "method_closed": None,
            }
        )

    closed = _has_any(low, _CLOSED_WORDS)
    open_ = _has_any(low, _OPEN_WORDS)
    networks = []
    if closed:
        networks.append({"id": "closed", "name": "закрытая сеть", "trust": "closed"})
    if open_:
        networks.append({"id": "open", "name": "открытая сеть", "trust": "open"})

    unknowns = ["направление/режим каждого потока (regex-фолбэк)"]

    return {
        "networks": networks,
        "flows": flows,
        "unknowns": unknowns,
        "assumptions": [],
    }


def _parse_json_lenient(text: str) -> dict:
    """Вытаскивает первый JSON-объект из ответа модели (терпимо к обёрткам)."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # пробуем вырезать от первой { до последней }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("Не удалось распарсить JSON из ответа модели")


_METHOD_MODES = {"manual": "manual", "usb": "USB", "pull": "PULL", "push": "PUSH"}
_FILE_PROTOCOLS = {"SFTP", "FTP", "SMB"}
RECIPROCAL_FILES = re.compile(
    r"\bфайл\w*[^.!?;]{0,40}\b(?:в обе стороны|в обоих направлениях)\b"
    r"|\bдвусторонн\w*\s+(?:файловый обмен|обмен файлами)\b", re.I,
)
FILE_METHOD_EVIDENCE = re.compile(
    r"\b(?:sftp|smb|ftp|usb|pull|push|manual|флеш\w*|носител\w*|вручную|ручн\w*|автомат\w*|"
    r"расписани\w*|забира\w*|забер\w*|скач\w*|загру\w*|выгру\w*|принос\w*|достав\w*)\b", re.I,
)

# Канонический словарь проверок (как в бенчмарках и методике).
_CHECK_CANON = (
    "маска имени",
    "тип и расширение",
    "размер",
    "целостность",
    "ICAP: внешний антивирус",
    "ICAP: песочница",
    "ICAP: DLP",
)


def _canonical_check(text: str) -> str:
    """Приводит проверку к канонической формулировке (в т.ч. с английского)."""
    key = " ".join(str(text).replace("_", " ").strip().lower().split())
    if not key:
        return ""
    if "встроенн" in key and "антивирус" in key:
        return str(text).strip()
    # Profile parameters affect whether two rules can share a check configuration.
    parameter = re.match(r"^(маска имени|размер|тип и расширение|целостность)\s*[:=]\s*(.+)$",
                         str(text).strip(), re.I)
    if parameter:
        return f"{parameter[1].casefold()}: {parameter[2].strip()}"
    # точные синонимы
    exact = {
        "маска имени": "маска имени",
        "mask name": "маска имени",
        "mask": "маска имени",
        "размер": "размер",
        "size": "размер",
        "тип и расширение": "тип и расширение",
        "тип/расширение": "тип и расширение",
        "целостность": "целостность",
        "integrity": "целостность",
        "icap:антивирус": "ICAP: внешний антивирус",
        "icap: антивирус": "ICAP: внешний антивирус",
        "icap: внешний антивирус": "ICAP: внешний антивирус",
        "антивирус": "ICAP: внешний антивирус",
        "внешний антивирус": "ICAP: внешний антивирус",
        "antivirus": "ICAP: внешний антивирус",
        "песочница": "ICAP: песочница",
        "sandbox": "ICAP: песочница",
        "icap: песочница": "ICAP: песочница",
        "dlp": "ICAP: DLP",
        "icap: dlp": "ICAP: DLP",
    }
    if key in exact:
        return exact[key]
    # частичные совпадения
    if "маск" in key or "mask" in key:
        return "маска имени"
    if "размер" in key or "size" in key:
        return "размер"
    if "целост" in key or "integrity" in key:
        return "целостность"
    if "песочниц" in key or "sandbox" in key:
        return "ICAP: песочница"
    if "dlp" in key:
        return "ICAP: DLP"
    if "антивирус" in key or "antivirus" in key:
        return "ICAP: внешний антивирус"
    if "тип" in key or "расширен" in key or "extension" in key:
        return "тип и расширение"
    return str(text).strip()


def _norm_methods(value: Any) -> list[dict] | None:
    """Приводит source_methods/target_methods к модели A (FileMethod)."""
    if not isinstance(value, list):
        return None
    out: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        mode = _METHOD_MODES.get(str(item.get("mode") or "").strip().lower())
        if mode is None:
            continue
        proto = item.get("protocol")
        proto = proto.upper() if isinstance(proto, str) else None
        if proto not in _FILE_PROTOCOLS:
            proto = None
        trigger = item.get("trigger")
        if trigger not in ("arrival", "schedule"):
            trigger = None
        storage = item.get("storage")
        out.append(
            {
                "mode": mode,
                "protocol": proto,
                "storage": storage.strip() if isinstance(storage, str) and storage.strip() else None,
                "trigger": trigger,
            }
        )
    return out or None


def _norm_checks(value: Any) -> list[str] | None:
    """Список проверок в канонической формулировке.

    None — сторона не определена; [] — явно без проверок. Разница важна для A:
    при None он задаёт уточняющий вопрос, при [] — принимает как есть.
    """
    if value is None:
        return None
    items = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in items:
        if isinstance(item, dict):
            item = (
                item.get("type")
                or item.get("name")
                or item.get("check")
                or item.get("value")
                or ""
            )
        canon = _canonical_check(item)
        if canon:
            result.append(canon)
    # убрать дубли, сохранив порядок
    seen: set[str] = set()
    return [x for x in result if not (x in seen or seen.add(x))]


_MANUAL_ROLES = ("подрядчик", "инженер", "сотрудник", "оператор", "специалист", "администратор")

# Текстовые маркеры проверок — страховка, если модель не заполнила профиль.
_CHECK_TEXT_MARKERS = (
    ("маск", "маска имени"),
    ("имени файла", "маска имени"),
    ("проверять имя файла", "маска имени"),
    ("размер", "размер"),
    ("целост", "целостность"),
    ("расширен", "тип и расширение"),
    ("тип файла", "тип и расширение"),
    ("песочниц", "ICAP: песочница"),
    ("dlp", "ICAP: DLP"),
    ("антивирус", "ICAP: внешний антивирус"),
)


def _checks_from_text(text: str) -> list[str]:
    """Проверки, упомянутые в исходном тексте (для страховки)."""
    low = text.lower()
    found: list[str] = []
    for clause in re.split(r"[.!?;\n]", low):
        if re.search(r"\b(?:без|нет|не)\b", clause):
            continue
        for marker, canon in _CHECK_TEXT_MARKERS:
            if marker in clause and canon not in found:
                found.append(canon)
    return found


FILE_REVERSE_BAN = re.compile(
    r"\b(?:файлы\s+(?:обратно\s+)?не\s+переда\w*|обратно\s+файлы\s+не\s+переда\w*|"
    r"обратной\s+(?:файловой\s+передачи|передачи\s+файлов)\s+нет|"
    r"на\s+флешк\w*\s+ничего\s+не\s+выгружа\w*|"
    r"у\s+файл\w*\s+обратной\s+передачи\s+нет)\b",
    re.I,
)


_CHECK_SIDE = re.compile(
    r"\s*(?:на\s+(?:(?P<before>[^,]+?)\s+стороне|стороне\s+(?P<after>[\w-]+))|"
    r"у\s+(?P<role>отправителя|получателя))\s+(?P<checks>.+)"
)
_NO_FILE_CHECKS = re.compile(
    r"(?:дополнительн\w*\s+)?провер(?:ок|ки)\s+(?:нет|не\s+(?:нужн|требу)\w*)"
    r"|без\s+(?:дополнительн\w*\s+)?проверок"
)


def _ground_file_check_absence(flows, networks, text):
    """Restore an explicit empty profile only when its workflow and side are clear."""
    file_flows = [flow for flow in flows if flow.get("type") == "file"]
    if not file_flows:
        return

    def stems(label):
        return {word[:4] for word in re.findall(r"[а-яё-]+", label.casefold()) if len(word) >= 4}

    network_stems = {
        network["id"]: stems(network["name"]) - {"стор", "сети", "сете", "сегм", "откр", "закр"}
        for network in networks
    }
    for network in networks:
        role = {"open": "откр", "closed": "закр"}.get(network.get("trust"))
        if role:
            network_stems[network["id"]].add(role)
    storage_names = [
        {method["storage"].casefold() for key in ("source_methods", "target_methods")
         for method in flow.get(key) or [] if len(method.get("storage") or "") >= 4}
        for flow in file_flows
    ]
    active = file_flows[0] if len(file_flows) == 1 else None
    for clause in re.split(r"[.!?;\n]+|,\s*(?=на\b|у\b)|\s+(?:а|и)\s+(?=на\b|у\b)", text.casefold()):
        matches = [flow for flow, names in zip(file_flows, storage_names)
                   if any(re.search(rf"(?<!\w){re.escape(name)}(?!\w)", clause) for name in names)]
        if matches or re.search(r"\bв\s+обратн\w*\s+(?:сторон\w*|направлени\w*)", clause):
            active = matches[0] if len(matches) == 1 else None
        match = _CHECK_SIDE.fullmatch(clause.strip())
        if active is None or not match or not _NO_FILE_CHECKS.fullmatch(match["checks"]):
            continue
        role = match["role"]
        if role:
            fields = ["source_checks" if role == "отправителя" else "target_checks"]
        else:
            side = stems(match["before"] or match["after"])
            fields = [field for endpoint, field in (("from", "source_checks"), ("to", "target_checks"))
                      if side & network_stems.get(active.get(endpoint), set())]
        if len(fields) == 1 and active[fields[0]] is None:
            active[fields[0]] = []


def _normalize_flows(data: dict, text: str = "") -> None:
    """Нормализует слоты под модель участка A (rules.Flow / rules.Session).

    Гарантирует всё, что читает b_adapter участка A:
    - from/to/initiator_network_id — только id объявленных сетей;
    - port — целое 1..65535 или None (у A строгая валидация);
    - source_methods/target_methods — по модели FileMethod (manual/USB/PULL/PUSH);
    - source_checks/target_checks — канонические списки с сохранением неизвестной стороны;
    - access_group = "shared" при одном пользователе или чистой автоматике;
    - USB-поток направляется от открытой сети к закрытой (Узел А);
    - manual_file_users / requests_for_vendor на верхнем уровне.
    """
    networks = data.get("networks") or []
    net_ids = {n.get("id") for n in networks if isinstance(n, dict) and n.get("id")}
    open_id = next(
        (n.get("id") for n in networks if isinstance(n, dict) and n.get("trust") == "open"),
        None,
    )
    closed_id = next(
        (n.get("id") for n in networks if isinstance(n, dict) and n.get("trust") == "closed"),
        None,
    )
    flows = [f for f in data.get("flows", []) if isinstance(f, dict)]
    directions_only = RECIPROCAL_FILES.search(text) and not FILE_METHOD_EVIDENCE.search(text)

    for flow in flows:
        # Firmware and software packages are files even before the delivery method is known.
        label = (flow.get("description") or "").casefold()
        if flow.get("type") == "data" and flow.get("protocol") in (None, "unknown") and re.search(
            r"\b(?:обновлени[яйе]|прошивк[аиу]|дистрибутивы?)\b", label
        ) and not re.search(r"\b(?:статус|состояни|показан|телеметр|журнал|событи)\w*", label):
            flow["type"] = "file"

    # --- проход 1: ссылки на сети, порт, способы передачи ---
    for f in flows:
        for key in ("from", "to", "initiator_network_id"):
            if f.get(key) not in net_ids:
                f[key] = None
        if f.get("initiator_network_id") is None and f.get("from") in net_ids:
            f["initiator_network_id"] = f["from"]
        # Two directions say nothing about manual access, USB or automation.
        if directions_only and f.get("type") == "file":
            for field in ("source_methods", "target_methods", "method_open", "method_closed"):
                f[field] = None

        port = f.get("port")
        try:
            port = int(port) if port is not None else None
        except (TypeError, ValueError):
            port = None
        f["port"] = port if port is not None and 1 <= port <= 65535 else None

        f["source_methods"] = [
            method for method in _norm_methods(f.get("source_methods")) or [] if method["mode"] != "PUSH"
        ] or None
        f["target_methods"] = [
            method for method in _norm_methods(f.get("target_methods")) or [] if method["mode"] != "PULL"
        ] or None

        # A подписывает PUSH как «автоматически при поступлении» только при
        # trigger=arrival. Поступление по факту есть лишь у USB-потока;
        # для сетевой ручной передачи подпись — «автоматически».
        has_usb = any(
            m.get("mode") == "USB"
            for m in (f["source_methods"] or []) + (f["target_methods"] or [])
        )
        explicit_arrival = re.search(r"при\s+поступлени|после\s+поступлени", text, re.I)
        if not has_usb and not explicit_arrival:
            for m in (f["source_methods"] or []) + (f["target_methods"] or []):
                if m.get("mode") == "PUSH":
                    m["trigger"] = None

    for flow in flows:
        if flow.get("type") != "file" or flow.get("mode") != "two-way":
            continue
        # Two explicitly opposite PULL → PUSH pipelines already represent the return trip.
        if (any(m["mode"] == "PULL" for m in flow["source_methods"] or [])
                and any(m["mode"] == "PUSH" for m in flow["target_methods"] or [])
                and any(other is not flow and other.get("type") == "file"
                        and other.get("from") == flow.get("to") and other.get("to") == flow.get("from")
                        for other in flows)):
            flow["mode"] = "one-way"

    _complete_explicit_file_methods(flows, networks, text)
    _preserve_explicit_access_groups(flows, text)
    _preserve_explicit_data_recipients(data, flows, networks, text)

    # --- люди, передающие файлы вручную/USB (бонусный подсчёт) ---
    has_manual = any(
        m.get("mode") in ("manual", "USB")
        for f in flows
        for m in (f.get("source_methods") or []) + (f.get("target_methods") or [])
    )
    mfu = data.get("manual_file_users")
    if isinstance(mfu, str):
        mfu = [mfu]
    users = [str(x).strip() for x in mfu if str(x).strip()] if isinstance(mfu, list) else []
    if not users and has_manual and text:
        low = text.lower()
        users = [role for role in _MANUAL_ROLES if role in low]
    data["manual_file_users"] = users or ([] if re.search(
        r"ручных\s+пользователей\s+нет|без\s+ручных\s+пользователей", text, re.I
    ) else None)
    data["same_file_checks"] = bool(re.search(
        r"проверки\s+одинаковы[еи]|одинаковые\s+проверки|разных профил\w* проверок\s+нет",
        text, re.I,
    ))

    # --- проход 2: проверки, доступ, USB, дефолты ---
    text_checks = _checks_from_text(text)
    one_file_flow = sum(f.get("type") == "file" for f in flows) == 1
    explicit_no_checks = not text_checks and bool(re.search(
        r"без проверок\s+(?:с обеих сторон|на обеих сторонах)|"
        r"оба направления\s+без проверок|(?:^|[.!?;\n]\s*)проверки\s+не требуются(?=$|[.!?;\n])",
        text, re.I,
    ))
    concrete_checks = text_checks or _NO_FILE_CHECKS.search(text.casefold()) or re.search(r"\bICAP\b", text, re.I)
    for f in flows:
        f["source_checks"] = _norm_checks(f.get("source_checks"))
        f["target_checks"] = _norm_checks(f.get("target_checks"))
        if f.get("type") == "file" and (directions_only or data["same_file_checks"]) and not concrete_checks:
            # The user's description gives the scope of the exchange, but no check profile.
            f["source_checks"] = f["target_checks"] = None
        if f.get("type") == "file" and explicit_no_checks:
            for field in ("source_checks", "target_checks"):
                if f[field] is None:
                    f[field] = []
        # A general sentence is ambiguous when several file workflows exist.
        if (
            f.get("type") == "file" and one_file_flow
            and f["source_checks"] is None and f["target_checks"] is None
            and text_checks
        ):
            f["source_checks"] = list(text_checks)

        # A single file flow with checks explicitly required before transfer
        # must retain every named check even if extraction found only some.
        if f.get("type") == "file" and one_file_flow and "перед передачей" in text.casefold() and text_checks:
            target_checks = f["target_checks"] or []
            source_checks = f["source_checks"] or []
            heard = [check for check in text_checks if check not in target_checks]
            f["source_checks"] = list(dict.fromkeys(source_checks + heard))
            if f["target_checks"] is not None:
                f["target_checks"] = target_checks

        access = f.get("access_group")
        f["access_group"] = access.strip() if isinstance(access, str) and access.strip() else None
        if f.get("type") == "file":
            explicit_shared = re.search(
                r"общ(?:ий|ая|его)\s+(?:доступ|видимость)|видимость\s+(?:файлов\s+)?общая|"
                r"раздел(?:ять|ение)\s+(?:доступ\w*\s+(?:к\s+файлам\s+)?)?не\s+нужн|"
                r"разных\s+групп\s+доступа[^.!?;]{0,65}\bнет\b|"
                r'"access_group"\s*:\s*"shared"',
                text, re.I,
            )
            if f["access_group"] is None and (len(users) == 1 or explicit_shared):
                f["access_group"] = "shared"
            elif (f["access_group"] == "shared" and not explicit_shared and not users
                  and f["source_methods"] is None and f["target_methods"] is None):
                f["access_group"] = None

        # USB есть только на Узле А (обращён к открытой сети).
        if open_id and closed_id:
            src_usb = any(m.get("mode") == "USB" for m in (f["source_methods"] or []))
            tgt_usb = any(m.get("mode") == "USB" for m in (f["target_methods"] or []))
            unresolved_endpoints = not f.get("from") or not f.get("to") or f["from"] == f["to"]
            if src_usb and not tgt_usb and unresolved_endpoints:
                f["from"], f["to"] = open_id, closed_id
            elif tgt_usb and not src_usb and unresolved_endpoints:
                f["from"], f["to"] = closed_id, open_id

        f.setdefault("recipient", None)
        f.setdefault("application_protocol", None)
        reverse = f.get("reverse_forbidden")
        if f.get("type") == "file" and one_file_flow and f.get("from") and f.get("to"):
            explicit_file_reverse_ban = FILE_REVERSE_BAN.search(text)
            if reverse is True or explicit_file_reverse_ban:
                reverse = True
                f["mode"] = "one-way"
        f["reverse_forbidden"] = reverse if isinstance(reverse, bool) else None
        f.setdefault("checks", [])
        f.setdefault("method_open", None)
        f.setdefault("method_closed", None)

    _ground_file_check_absence(flows, networks, text)
    data["flows"] = flows

    # Потребности для разработчика продукта.
    rfv = data.get("requests_for_vendor")
    if isinstance(rfv, str):
        rfv = [rfv]
    data["requests_for_vendor"] = (
        [str(x).strip() for x in rfv if str(x).strip()] if isinstance(rfv, list) else []
    )


def _stitch_file_delivery(flows, text):
    """Join one explicit delivery continuation to its cross-network transfer."""
    files = [flow for flow in flows if flow.get("type") == "file"]
    if len(files) != 2 or not re.search(
        r"\b(?:там|на принимающей стороне|в закрытом сегменте)\b[^.!?;]{0,110}"
        r"\bдоставля\w*\s+их\b",
        text, re.I,
    ):
        return
    crossing = [flow for flow in files if flow.get("from") and flow.get("to") and flow["from"] != flow["to"]]
    if len(crossing) != 1:
        return
    transfer = crossing[0]
    delivery = next(flow for flow in files if flow is not transfer)
    destination_side = transfer["to"]
    delivery_sides = {delivery.get("from"), delivery.get("to")} - {None}
    if delivery_sides - {destination_side}:
        return
    target_methods = delivery.get("target_methods") or []
    explicit_destination = re.search(
        r"\bдоставля\w*\s+их\s+(?:в|на)\s+([^.!?;]{2,95}?)\s+по\s+(SMB|SFTP|FTP)\b",
        text, re.I,
    )
    if explicit_destination:
        target_methods = [{"mode": "PUSH", "storage": explicit_destination[1], "protocol": explicit_destination[2].upper()}]
    if not target_methods or any(method["mode"] != "PUSH" for method in target_methods):
        return
    previous_methods = transfer.get("target_methods") or []
    if len(previous_methods) > 1 and previous_methods != target_methods:
        return
    transfer["target_methods"] = target_methods
    for key in ("recipient", "target_checks", "access_group"):
        if transfer.get(key) is None:
            transfer[key] = delivery.get(key)
    flows[:] = [flow for flow in flows if flow is not delivery]


def _ground_file_destination(flow, networks, text):
    """Use an explicit file destination to resolve a reversed model extraction."""
    if len(networks) != 2 or flow.get("mode") == "two-way":
        return
    matches = re.findall(
        r"\b(?:обновлени\w*|файл\w*|прошивк\w*)\s+"
        r"(?:переда\w*\s+)?(?:в|на)\s+"
        r"((?:(?:закрыт\w*|открыт\w*)\s+)?[а-яё-]+(?:\s+[а-яё-]+)?)",
        text, re.I,
    )
    if len(matches) != 1:
        return
    words = re.findall(r"[а-яё-]+", matches[0].casefold())
    generic = ("сет", "сегмент")
    roots = [word[:4] for word in words if not word.startswith(generic)]
    if not roots:
        return
    options = []
    for network in networks:
        name = network["name"].casefold()
        if any(root in {"откр", "закр"} for root in roots):
            role = "closed" if "закр" in roots else "open"
            if network.get("trust") == role:
                options.append(network["id"])
        elif re.search(rf"\b{re.escape(roots[0])}", name):
            options.append(network["id"])
    if len(options) == 1:
        target = options[0]
        source = next(network["id"] for network in networks if network["id"] != target)
        if flow.get("to") != target:
            flow.update({"from": source, "to": target, "initiator_network_id": source})


def _join_symmetric_file_steps(flows, files):
    """Join one extracted PULL step and one PUSH step of the same directed route."""
    for direction in dict.fromkeys((flow.get("from"), flow.get("to")) for flow in files):
        source, target = direction
        if not source or not target or source == target:
            continue
        steps = [flow for flow in files if (flow.get("from"), flow.get("to")) == direction]
        if len(steps) != 2:
            continue
        pull, push = sorted(steps, key=lambda flow: not flow.get("source_methods"))
        sending, receiving = pull.get("source_methods") or [], push.get("target_methods") or []
        if (pull.get("target_methods") or push.get("source_methods") or
                [method["mode"] for method in sending] != ["PULL"] or
                [method["mode"] for method in receiving] != ["PUSH"]):
            continue
        fields = ("access_group", "source_checks", "target_checks", "reverse_forbidden")
        if any(pull.get(key) is not None and push.get(key) is not None and pull[key] != push[key]
               for key in fields):
            continue
        for key in fields:
            if pull.get(key) is None:
                pull[key] = push.get(key)
        pull.update(target_methods=receiving, recipient=push.get("recipient") or receiving[0].get("storage"))
        flows[:] = [flow for flow in flows if flow is not push]
        files[:] = [flow for flow in files if flow is not push]


def _complete_explicit_file_methods(flows, networks, text):
    _stitch_file_delivery(flows, text)
    file_flows = [flow for flow in flows if flow.get("type") == "file"]
    if len(file_flows) == 1:
        _ground_file_destination(file_flows[0], networks, text)
        flow = file_flows[0]
        incoming_usb = re.search(
            r"\bпринос\w*[^.!?;]{0,45}\bна\s+флешк\w*|"
            r"\b(?:с\s+флешк\w*|по\s+USB)\s+(?:загружа\w*|переда\w*)",
            text, re.I,
        )
        if incoming_usb and not re.search(r"\b(?:SFTP|PULL)\b|\bвручную\b", text, re.I):
            flow["source_methods"] = [{"mode": "USB"}]
        destination = re.search(
            r"\bавтоматически\s+(?:доставля\w*|попада\w*)(?:\s+их)?\s+(?:в|на)\s+"
            r"([^.!?;]{2,95}?)\s+по\s+(SMB|SFTP|FTP)\b",
            text, re.I,
        )
        if destination:
            methods = flow["target_methods"] or []
            push = next((m for m in methods if m["mode"] == "PUSH"), None)
            if push is None and len(methods) <= 1:
                push = {"mode": "PUSH"}
                flow["target_methods"] = [push]
            if push is not None:
                push["storage"], push["protocol"] = destination[1], destination[2].upper()
    if re.search(r"автоматизаци\w*\s+нет|без автоматизаци\w*", text, re.I):
        for flow in file_flows:
            source = flow["source_methods"] or []
            if not flow["target_methods"] and any(method["mode"] == "manual" for method in source):
                flow["target_methods"] = [{"mode": "manual", "protocol": "SFTP"}]

    symmetric_automation = bool(re.search(
        r"\b(?:забира\w*|забор|выгружа\w*)[^.!?;]{0,120}\bиз\s+(?:каждого|обоих)\b"
        r"[^.!?;]{0,240}\b(?:во\s+второе|в\s+другое|в\s+противоположное)\b",
        text, re.I,
    ))
    reciprocal_intent = symmetric_automation or bool(RECIPROCAL_FILES.search(text))
    if len(networks) != 2 or not file_flows or not reciprocal_intent:
        return

    if symmetric_automation:
        _join_symmetric_file_steps(flows, file_flows)
    network_ids = {network["id"] for network in networks}
    directed = [flow for flow in file_flows if {flow.get("from"), flow.get("to")} == network_ids]
    directions = {(flow["from"], flow["to"]) for flow in directed}
    if len(directions) == 1 and len(directed) == len(file_flows):
        source, target = next(iter(directions))
        if not any(flow.get("reverse_forbidden") is True for flow in directed):
            # The requirement is explicit. Only the symmetric case proves the reverse settings.
            prototype = directed[0]
            mergeable = symmetric_automation and len(directed) == 1
            reverse = {
                "id": None, "type": "file", "from": target, "to": source,
                "mode": "one-way", "source_methods": None, "target_methods": None,
                "description": "Обратная передача файлов",
                "access_group": prototype.get("access_group") if mergeable else None,
                "source_checks": prototype.get("target_checks") if mergeable else None,
                "target_checks": prototype.get("source_checks") if mergeable else None,
            }
            if mergeable:
                reverse["source_device"] = prototype.get("recipient")
                reverse["recipient"] = prototype.get("source_device")
            flows.append(reverse)
            file_flows.append(reverse)
            for flow in directed:
                flow["mode"] = "one-way"
    if not symmetric_automation or len(file_flows) != 2:
        return
    first, second = file_flows
    if (first.get("from"), first.get("to")) != (second.get("to"), second.get("from")):
        return
    if any(flow.get("reverse_forbidden") is True for flow in file_flows):
        return

    protocols = [name for name in _FILE_PROTOCOLS if re.search(rf"\b{name}\b", text, re.I)]
    names = {network["id"]: network["name"] for network in networks}
    for flow, opposite in ((first, second), (second, first)):
        for field, other_field, mode, other_mode, side, trigger in (
            ("source_methods", "target_methods", "PULL", "PUSH", "from", "schedule"),
            ("target_methods", "source_methods", "PUSH", "PULL", "to", "arrival"),
        ):
            current = next((m for m in flow[field] or [] if m["mode"] == mode), None)
            counterpart = next((m for m in opposite[other_field] or [] if m["mode"] == other_mode), None)
            candidates = flow[field] or []
            if current is None and len(candidates) > 1:
                continue
            method = current or {**(candidates[0] if candidates else {}), "mode": mode}
            if not method.get("protocol") and len(protocols) == 1:
                method["protocol"] = protocols[0]
            if not method.get("storage"):
                method["storage"] = (counterpart or {}).get("storage") or f"Хранилище сети «{names[flow[side]]}»"
            if not method.get("trigger") and (
                trigger == "schedule" and re.search(r"по расписани", text, re.I)
                or trigger == "arrival" and re.search(r"при поступлени|после поступлени", text, re.I)
            ):
                method["trigger"] = trigger
            if current is None:
                flow[field] = [method]
        if flow["source_methods"] and flow["target_methods"]:
            flow["mode"] = "one-way"


def _preserve_explicit_access_groups(flows, text):
    group_count = re.search(r"\b(два|три|четыре|[0-9]{1,3})\s+(?:отдела|отделов|группы|групп)\b", text, re.I)
    if not group_count or not re.search(r"не\s+должны\s+видеть|разделить\s+доступ", text, re.I):
        return
    file_flows = [flow for flow in flows if flow.get("type") == "file"]
    if not file_flows or len({(flow.get("from"), flow.get("to")) for flow in file_flows}) != 1:
        return
    count_word = group_count[1].casefold()
    count = int(count_word) if count_word.isdecimal() else {"два": 2, "три": 3, "четыре": 4}[count_word]
    if len(file_flows) > count or not 2 <= count <= 256:
        return
    if len(file_flows) == 1 and re.search(r"проверки\s+одинаковы[еи]", text, re.I):
        for _ in range(count - 1):
            new_flow = {**file_flows[0], "id": None}
            flows.append(new_flow)
            file_flows.append(new_flow)
    if len(file_flows) != count:
        return
    assigned = set()
    for index, flow in enumerate(file_flows, 1):
        group = flow.get("access_group")
        if not isinstance(group, str) or group.casefold() in assigned | {"shared", ""}:
            group = f"Группа {index}"
        flow["access_group"] = group
        assigned.add(group.casefold())


def _preserve_explicit_data_recipients(data, flows, networks, text):
    generic_names = {str(network.get("name") or "").casefold() for network in networks}
    generic_names.update({"офис", "цех", "office", "shop", "open", "closed"})
    roles = {
        "MQTT": (r"\bброкеру\s+(офиса|цеха|диспетчерской|склада)\b", "Брокер {}"),
        "UDP": (r"\bжурнал\w*[^.!?;]{0,65}\b(?:одному\s+)?офисному\s+серверу\b", "Офисный сервер"),
    }
    confirmed_unknown_ports = []
    for protocol, (pattern, label) in roles.items():
        selected = [flow for flow in flows if flow.get("type") == "data"
                    and str(flow.get("protocol")).upper() == protocol]
        if len(selected) != 1:
            continue
        flow = selected[0]
        if re.search(rf"\bпорт\s+{protocol}\s+неизвестен\b|\bпорт\s+{protocol}\s+не\s+указан\b", text, re.I):
            flow["port"] = None
            confirmed_unknown_ports.append(protocol)
        recipient = str(flow.get("recipient") or "").strip().casefold()
        if not recipient or recipient in generic_names:
            matches = list(re.finditer(pattern, text, re.I))
            if len(matches) == 1:
                flow["recipient"] = label.format(*matches[0].groups())
                flow["recipient_confirmed_role"] = True
    data["confirmed_unknown_ports"] = confirmed_unknown_ports


def _required_object(properties):
    return {
        "type": "object", "properties": properties,
        "required": list(properties), "additionalProperties": False,
    }


def _array(items):
    return {"type": "array", "items": items}


def _nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


_STRING = {"type": "string"}
_OPTIONAL_STRING = _nullable(_STRING)
_METHOD_SCHEMA = _required_object({
    "mode": {"type": "string", "enum": ["manual", "USB", "PULL", "PUSH"]},
    "protocol": _OPTIONAL_STRING, "storage": _OPTIONAL_STRING, "trigger": _OPTIONAL_STRING,
})
EXTRACTION_SCHEMA = _required_object({
    "networks": _array(_required_object({
        "id": _STRING, "name": _STRING, "trust": {"type": "string", "enum": ["open", "closed", "unknown"]},
    })),
    "flows": _array(_required_object({
        "id": _OPTIONAL_STRING,
        "type": _nullable({"type": "string", "enum": ["data", "file"]}),
        "from": _OPTIONAL_STRING, "to": _OPTIONAL_STRING, "mode": _OPTIONAL_STRING,
        "protocol": _OPTIONAL_STRING, "port": _nullable({"type": "integer"}),
        "application_protocol": _OPTIONAL_STRING, "description": _OPTIONAL_STRING,
        "source_device": _OPTIONAL_STRING, "recipient": _OPTIONAL_STRING,
        "initiator_network_id": _OPTIONAL_STRING, "reverse_forbidden": _nullable({"type": "boolean"}),
        "source_methods": _nullable(_array(_METHOD_SCHEMA)), "target_methods": _nullable(_array(_METHOD_SCHEMA)),
        "source_checks": _nullable(_array(_STRING)), "target_checks": _nullable(_array(_STRING)),
        "access_group": _OPTIONAL_STRING,
    })),
    "manual_file_users": _nullable(_array(_STRING)),
    "requests_for_vendor": _array(_STRING),
    "unknowns": _array(_STRING), "assumptions": _array(_STRING),
})


def _decode_extraction(reply):
    data = _parse_json_lenient(reply)
    if not isinstance(data, dict) or any(not isinstance(data.get(field), list) for field in ("networks", "flows")):
        raise ValueError("Ожидался объект со списками сетей и потоков.")
    networks = {}
    for network in data["networks"]:
        if not isinstance(network, dict) or any(
            not isinstance(network.get(field), str) or not network[field].strip()
            for field in ("id", "name")
        ):
            raise ValueError("У каждой сети должны быть идентификатор и имя.")
        network_id = network["id"]
        if network_id in networks and network != networks[network_id]:
            raise ValueError("Несколько разных сетей получили один идентификатор.")
        networks[network_id] = network
    data["networks"] = list(networks.values())
    if any(not isinstance(flow, dict) for flow in data["flows"]):
        raise ValueError("Каждый поток должен быть объектом.")
    return data


DATA_ENDPOINT_PATTERN = re.compile(
    r"\b(Modbus\s+TCP|МЭК[- ]?104|MQTT|NTP|TCP|UDP)\b"
    r"(?:\s*(?:порт\w*\s*)?[:=]?\s*([0-9]{1,5})\b)?",
    re.I,
)


def _explicit_data_requirements(text):
    """Only use named transport/port pairs and explicit protocol requests."""
    required = set()
    for clause in re.split(r"[.!?;\n]+", text):
        ntp = bool(re.search(
            r"\bпо\s+NTP\b|\bNTP\s*,?\s*UDP\s*123\b|"
            r"\bNTP[- ]сервер\w*[^.!?;]{0,100}\b(?:время|синхронизаци\w*)\b",
            clause, re.I,
        ))
        for match in DATA_ENDPOINT_PATTERN.finditer(clause):
            before = clause[:match.start()]
            after = clause[match.end():]
            if re.search(r"\b(?:не|без|запретить|не используем)\s+$", before, re.I) or re.match(
                r"\s+не\s+(?:нуж\w*|требу\w*|использу\w*)\b", after, re.I,
            ):
                continue
            name = match[1].upper().replace("-", " ")
            port = int(match[2]) if match[2] else None
            if port is not None and not 1 <= port <= 65535:
                continue
            if name == "UDP" and port == 123 and ntp:
                name = "NTP"
            if port is not None or re.search(r"\bпо\s+$", clause[:match.start()], re.I):
                required.add((name, port))
    return {(name, port) for name, port in required if port is not None or not any(
        other == name and number is not None for other, number in required
    )}


def _flow_protocol(flow):
    protocol = str(flow.get("application_protocol") or "").strip().upper()
    return "NTP" if protocol == "NTP" else str(flow.get("protocol") or "").upper().replace("-", " ")


def _missing_intents(data, evidence):
    flows = data["flows"]
    data_flows = [flow for flow in flows if flow.get("type") == "data"]
    expected = _explicit_data_requirements(evidence)
    for name, port in expected:
        exact = [flow for flow in data_flows if _flow_protocol(flow) == name]
        explicit_ports = {number for proto, number in expected if proto == name and number is not None}
        if port is not None and len(exact) == 1 and len(explicit_ports) == 1 and exact[0].get("port") is None:
            exact[0]["port"] = port
    missing = {
        (name, port) for name, port in expected
        if not any(_flow_protocol(flow) == name and (port is None or flow.get("port") == port) for flow in data_flows)
    }
    wants_files = bool(re.search(
        r"\b(?:переда\w*|доставля\w*|обменива\w*|загружа\w*)\s+"
        r"(?:\w+\s+){0,2}(?:файл\w*|обновлени\w*|прошивк\w*)\b",
        evidence, re.I,
    ))
    missing_file = wants_files and not any(flow.get("type") == "file" for flow in flows)
    return missing, missing_file


def _conflicting_file_directions(data, evidence):
    if not FILE_REVERSE_BAN.search(evidence):
        return []
    file_flows = [flow for flow in data["flows"] if flow.get("type") == "file"]
    directions = {(flow.get("from"), flow.get("to")) for flow in file_flows}
    return [
        flow for flow in file_flows
        if flow.get("from") and flow.get("to") and flow["from"] != flow["to"]
        and (flow["to"], flow["from"]) in directions
    ]


def _add_missing_intents(data, missing, missing_file):
    protocols = {"MODBUS TCP": "Modbus TCP", "МЭК 104": "МЭК 104"}
    for name, port in sorted(missing, key=lambda value: (value[0], value[1] or 0)):
        protocol = "UDP" if name == "NTP" else protocols.get(name, name)
        data["flows"].append({
            "id": None, "type": "data", "protocol": protocol, "port": port,
            "application_protocol": "NTP" if name == "NTP" else None,
            "description": f"Поток {name}" + (f" {port}" if port else ""),
        })
    if missing_file:
        data["flows"].append({"id": None, "type": "file", "description": "Упомянутый файловый обмен"})


def extract(
    client: LLMClient,
    text: str,
    *,
    session_id: str = "",
    turn_id: int = 0,
    use_llm: bool = True,
    evidence_text: str | None = None,
) -> dict[str, Any]:
    """Извлекает слоты из текста. При use_llm=False или ошибке — regex-фолбэк."""
    evidence = text if evidence_text is None else evidence_text
    if use_llm:
        try:
            messages = [
                {"role": "system", "content": prompts.SYSTEM_EXTRACT},
                {"role": "user", "content": text},
            ]
            used_retry = False
            try:
                reply, _rec = client.chat(
                    messages, purpose="extract", session_id=session_id, turn_id=turn_id,
                    temperature=0.0, max_tokens=4000, response_schema=EXTRACTION_SCHEMA,
                )
                data = _decode_extraction(reply)
            except Exception as error:
                schema_rejection = getattr(error, "status_code", None) == 400 and (
                    "json_validate_failed" in str(error) or "expected schema" in str(error)
                )
                if not schema_rejection and not isinstance(error, ValueError):
                    raise
                used_retry = True
                retry = [*messages, {
                    "role": "user", "content": "Перепроверь формат. Верни объект со списками networks и flows. "
                                              "У разных сетей должны быть разные идентификаторы.",
                }]
                reply, _rec = client.chat(
                    retry, purpose="extract", session_id=session_id, turn_id=turn_id,
                    temperature=0.0, max_tokens=4000,
                )
                data = _decode_extraction(reply)
            data.setdefault("unknowns", [])
            data.setdefault("assumptions", [])
            _normalize_flows(data, evidence)
            missing, missing_file = _missing_intents(data, evidence)
            conflicting = _conflicting_file_directions(data, evidence)
            if (missing or missing_file or conflicting) and not used_retry:
                expected = [f"{name} {port or ''}".strip() for name, port in sorted(missing, key=lambda item: (item[0], item[1] or 0))]
                if missing_file:
                    expected.append("файловый обмен")
                review_message = "Верни полный проект, сохрани все подтверждённые потоки."
                if expected:
                    review_message += " В предыдущем результате пропущены: " + ", ".join(expected) + "."
                if conflicting:
                    review_message += (
                        " В тексте запрещена обратная передача файлов. Убери придуманное встречное "
                        "направление; если встречный поток задан отдельно, сохрани оба как однонаправленные "
                        "и отметь запрет обратной передачи в каждом."
                    )
                try:
                    repaired, _rec = client.chat(
                        [*messages, {"role": "user", "content": review_message}],
                        purpose="extract", session_id=session_id, turn_id=turn_id,
                        temperature=0.0, max_tokens=4000, response_schema=EXTRACTION_SCHEMA,
                    )
                    reviewed = _decode_extraction(repaired)
                    _normalize_flows(reviewed, evidence)
                    still_missing, still_missing_file = _missing_intents(reviewed, evidence)
                    still_conflicting = _conflicting_file_directions(reviewed, evidence)
                    missing_score = len(missing) + missing_file + bool(conflicting)
                    new_score = len(still_missing) + still_missing_file + bool(still_conflicting)
                    allowed_removals = 1 if conflicting and not still_conflicting else 0
                    if (len(reviewed["flows"]) + allowed_removals >= len(data["flows"])
                            and still_missing <= missing and not (still_missing_file and not missing_file)
                            and new_score < missing_score):
                        data, missing, missing_file = reviewed, still_missing, still_missing_file
                        conflicting = still_conflicting
                except Exception as error:
                    logger.info("Coverage review unavailable: %s", type(error).__name__)
            if conflicting and not all(flow.get("reverse_forbidden") for flow in conflicting):
                for flow in conflicting:
                    flow["mode"] = None
            _add_missing_intents(data, missing, missing_file)
            return data
        except GroqRateLimit:
            raise
        except Exception as exc:  # noqa: BLE001
            # Падение LLM не должно ронять сессию — отдаём фолбэк, НО явно помечаем.
            data = quick_extract(evidence)
            _normalize_flows(data, evidence)
            data["_fallback"] = True
            data["_warning"] = (
                f"LLM-извлечение не удалось ({type(exc).__name__}, HTTP {getattr(exc, 'status_code', '?')}). "
                "Использован regex-фолбэк — качество ниже, направления/режимы не определены."
            )
            logger.warning("extract fallback: %s", data["_warning"])
            return data

    data = quick_extract(evidence)
    _normalize_flows(data, evidence)
    return data
