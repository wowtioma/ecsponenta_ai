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
from .client import LLMClient

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
    if "без проверок" in low:
        return []
    found: list[str] = []
    for marker, canon in _CHECK_TEXT_MARKERS:
        if marker in low and canon not in found:
            found.append(canon)
    return found


_REVERSE_MARKERS = (
    "обратно",
    "в обе стороны",
    "обе стороны",
    "двунаправ",
    "туда и обратно",
    "взаимн",
    "both directions",
)


def _has_reverse_markers(text: str) -> bool:
    """Есть ли в тексте явное указание на обратное направление."""
    low = text.casefold()
    return any(marker in low for marker in _REVERSE_MARKERS)


def _rescue_methods(text: str, flow: dict) -> None:
    """Страховка: модель не заполнила способы, но они названы в тексте.

    Слабая модель часто возвращает source_methods/target_methods = null, хотя
    в тексте прямо сказано «вручную по SFTP» и «автоматически доставляет в
    хранилище по SMB/PUSH». Тогда A задаёт лишние вопросы; здесь мы заполняем
    способы детерминированно.
    """
    if flow.get("type") != "file":
        return

    low = text.casefold()

    if not flow.get("source_methods"):
        if "вручную" in low and "sftp" in low:
            flow["source_methods"] = [
                {
                    "mode": "manual",
                    "protocol": "SFTP",
                    "storage": None,
                    "trigger": None,
                }
            ]

    if not flow.get("target_methods"):
        automatic = any(
            word in low
            for word in ("автоматически", "доставляет", "в хранилище")
        )
        if automatic and "smb" in low:
            flow["target_methods"] = [
                {
                    "mode": "PUSH",
                    "protocol": "SMB",
                    "storage": "хранилище",
                    "trigger": "arrival",
                }
            ]
        elif automatic:
            flow["target_methods"] = [
                {
                    "mode": "PUSH",
                    "protocol": None,
                    "storage": None,
                    "trigger": "arrival",
                }
            ]


def _drop_mirrored_flows(flows: list[dict], text: str) -> list[dict]:
    """Убирает выдуманный обратный поток, если обратного направления нет в тексте.

    Модель иногда дорисовывает пару «A → B» и «B → A», даже когда описан один
    поток. Если в тексте нет слов «обратно», «в обе стороны» и т. п., второй
    поток лишний: участок A сгенерирует по нему лишние уточняющие вопросы.
    """
    if len(flows) < 2 or _has_reverse_markers(text):
        return flows

    result: list[dict] = []
    for flow in flows:
        mirror = next(
            (
                other
                for other in result
                if other.get("type") == flow.get("type")
                and other.get("from") == flow.get("to")
                and other.get("to") == flow.get("from")
                and other.get("protocol") == flow.get("protocol")
                and other.get("port") == flow.get("port")
            ),
            None,
        )
        if mirror is not None:
            logger.info(
                "drop invented reverse flow %s -> %s",
                flow.get("from"),
                flow.get("to"),
            )
            continue
        result.append(flow)

    return result


def _normalize_flows(data: dict, text: str = "") -> None:  # dsh-skip-complexity dsh-skip-func-length
    """Нормализует слоты под модель участка A (rules.Flow / rules.Session).

    Гарантирует всё, что читает b_adapter участка A:
    - from/to/initiator_network_id — только id объявленных сетей;
    - port — целое 1..65535 или None (у A строгая валидация);
    - source_methods/target_methods — по модели FileMethod (manual/USB/PULL/PUSH);
    - source_checks/target_checks — канонические списки; если проверки заданы
      только с одной стороны, у второй явно фиксируется [] (A требует обе);
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
    file_flows = [f for f in flows if f.get("type") == "file"]

    # --- проход 1: ссылки на сети, порт, способы передачи ---
    for f in flows:
        for key in ("from", "to", "initiator_network_id"):
            if f.get(key) not in net_ids:
                f[key] = None
        if f.get("initiator_network_id") is None and f.get("from") in net_ids:
            f["initiator_network_id"] = f["from"]

        port = f.get("port")
        try:
            port = int(port) if port is not None else None
        except (TypeError, ValueError):
            port = None
        f["port"] = port if port is not None and 1 <= port <= 65535 else None

        f["source_methods"] = _norm_methods(f.get("source_methods"))
        f["target_methods"] = _norm_methods(f.get("target_methods"))

        # A подписывает PUSH как «автоматически при поступлении» только при
        # trigger=arrival. Поступление по факту есть лишь у USB-потока;
        # для сетевой ручной передачи подпись — «автоматически».
        has_usb = any(
            m.get("mode") == "USB"
            for m in (f["source_methods"] or []) + (f["target_methods"] or [])
        )
        if not has_usb:
            for m in (f["source_methods"] or []) + (f["target_methods"] or []):
                if m.get("mode") == "PUSH":
                    m["trigger"] = None

        # Страховка: способы названы в тексте, но модель их не заполнила.
        if len(file_flows) == 1 and f.get("type") == "file":
            _rescue_methods(text, f)

    # Выдуманный обратный поток (описан только один) убираем до расчёта правил.
    flows = _drop_mirrored_flows(flows, text)

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
    data["manual_file_users"] = users or None

    # --- проход 2: проверки, доступ, USB, дефолты ---
    text_checks = _checks_from_text(text)
    one_file_flow = sum(f.get("type") == "file" for f in flows) == 1
    for f in flows:
        f["source_checks"] = _norm_checks(f.get("source_checks"))
        f["target_checks"] = _norm_checks(f.get("target_checks"))
        if (f["source_checks"] is None) != (f["target_checks"] is None):
            # проверки заданы для одной стороны — у второй явно «без проверок»
            if f["source_checks"] is None:
                f["source_checks"] = []
            if f["target_checks"] is None:
                f["target_checks"] = []
        # Страховка: модель не заполнила проверки, но они есть в тексте.
        if (
            f.get("type") == "file"
            and not f["source_checks"]
            and not f["target_checks"]
            and text_checks
        ):
            f["source_checks"] = list(text_checks)
            f["target_checks"] = []

        # A single file flow with checks explicitly required before transfer
        # must retain every named check even if extraction found only some.
        if f.get("type") == "file" and one_file_flow and "перед передачей" in text.casefold() and text_checks:
            target_checks = f["target_checks"] or []
            source_checks = f["source_checks"] or []
            heard = [check for check in text_checks if check not in target_checks]
            f["source_checks"] = list(dict.fromkeys(source_checks + heard))
            f["target_checks"] = target_checks

        access = f.get("access_group")
        f["access_group"] = access.strip() if isinstance(access, str) and access.strip() else None
        manual_side = any(
            m.get("mode") in ("manual", "USB")
            for m in (f["source_methods"] or []) + (f["target_methods"] or [])
        )
        if f.get("type") == "file" and f["access_group"] is None:
            if len(users) == 1 or (not manual_side and not users):
                f["access_group"] = "shared"

        # USB есть только на Узле А (обращён к открытой сети).
        if open_id and closed_id:
            src_usb = any(m.get("mode") == "USB" for m in (f["source_methods"] or []))
            tgt_usb = any(m.get("mode") == "USB" for m in (f["target_methods"] or []))
            if src_usb:
                f["from"], f["to"] = open_id, closed_id
            elif tgt_usb:
                f["from"], f["to"] = closed_id, open_id

        f.setdefault("recipient", None)
        f.setdefault("application_protocol", None)
        reverse = f.get("reverse_forbidden")
        if f.get("type") == "file" and one_file_flow and f.get("from") and f.get("to"):
            explicit_file_reverse_ban = re.search(
                r"файлы\s+не\s+передаются|обратной\s+файловой\s+передачи\s+нет",
                text, re.I,
            )
            if reverse is True or explicit_file_reverse_ban:
                reverse = True
                f["mode"] = "one-way"
        f["reverse_forbidden"] = reverse if isinstance(reverse, bool) else None
        f.setdefault("checks", [])
        f.setdefault("method_open", None)
        f.setdefault("method_closed", None)

    # Поток внутри одной сети бессмыслен — выбрасываем.
    data["flows"] = [
        f
        for f in flows
        if not (f.get("from") is not None and f.get("from") == f.get("to"))
    ]

    # Потребности для разработчика продукта.
    rfv = data.get("requests_for_vendor")
    if isinstance(rfv, str):
        rfv = [rfv]
    data["requests_for_vendor"] = (
        [str(x).strip() for x in rfv if str(x).strip()] if isinstance(rfv, list) else []
    )


def extract(
    client: LLMClient,
    text: str,
    *,
    session_id: str = "",
    turn_id: int = 0,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Извлекает слоты из текста. При use_llm=False или ошибке — regex-фолбэк."""
    if use_llm:
        try:
            reply, _rec = client.chat(
                [
                    {"role": "system", "content": prompts.SYSTEM_EXTRACT},
                    {"role": "user", "content": text},
                ],
                purpose="extract",
                session_id=session_id,
                turn_id=turn_id,
                temperature=0.0,
                max_tokens=4000,
            )
            data = _parse_json_lenient(reply)
            data.setdefault("networks", [])
            data.setdefault("flows", [])
            data.setdefault("unknowns", [])
            data.setdefault("assumptions", [])
            _normalize_flows(data, text)
            return data
        except Exception as exc:  # noqa: BLE001
            # Падение LLM не должно ронять сессию — отдаём фолбэк, НО явно помечаем.
            data = quick_extract(text)
            _normalize_flows(data, text)
            data["_fallback"] = True
            data["_warning"] = (
                f"LLM-извлечение не удалось ({type(exc).__name__}: {str(exc)[:200]}). "
                "Использован regex-фолбэк — качество ниже, направления/режимы не определены."
            )
            logger.warning("extract fallback: %s", data["_warning"])
            return data

    data = quick_extract(text)
    _normalize_flows(data, text)
    return data
