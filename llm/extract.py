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
            return data
        except Exception as exc:  # noqa: BLE001
            # Падение LLM не должно ронять сессию — отдаём фолбэк, НО явно помечаем.
            data = quick_extract(text)
            data["_fallback"] = True
            data["_warning"] = (
                f"LLM-извлечение не удалось ({type(exc).__name__}: {str(exc)[:200]}). "
                "Использован regex-фолбэк — качество ниже, направления/режимы не определены."
            )
            logger.warning("extract fallback: %s", data["_warning"])
            return data
    return quick_extract(text)
