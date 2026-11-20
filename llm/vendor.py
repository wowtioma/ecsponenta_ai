"""Сбор потребностей для развития продукта (ТЗ §12.7, методика §7, бонус до 5).

Две категории, которые идут в поле requests_for_vendor служебного JSON:
  1) «неподдерживаемое» — пользователь просит то, чего нет в Синониксе 1.9;
  2) «другое» — ответ, вписанный пользователем в поле «другое» вручную.

Список «чего нет в продукте» берём из 01_scope_functions_synonyx_1.9.md (раздел
«Ограничения») и из бенчмарка O01. Не выдумываем.
"""
from __future__ import annotations

from typing import Any

# Маркеры «неподдерживаемого» -> пояснение. Ключ ищется в тексте без учёта регистра.
# Используем основы слов (стемы), чтобы ловить склонения: встроенн- → встроенный/ого/ым.
KNOWN_UNSUPPORTED: list[tuple[str, str]] = [
    ("маршрутизац", "маршрутизация трафика между сетями"),
    ("доступ на подсеть", "открытие доступа на подсеть/диапазон адресов"),
    ("диапазон адресов", "открытие доступа на диапазон адресов"),
    ("три сети", "проектирование более двух сетей"),
    ("третьей сети", "проектирование более двух сетей"),
    ("больше двух сет", "проектирование более двух сетей"),
    ("pam", "функции PAM-системы (запись действий конкретного человека)"),
    ("запись действий", "функции PAM-системы (запись действий конкретного человека)"),
    ("usb на узле в", "USB-носитель на Узле В (порт есть только на Узле А)"),
    ("флешку к узлу в", "USB-носитель на Узле В (порт есть только на Узле А)"),
]

_BUILTIN_AV_DESC = "встроенный антивирус (есть только внешние по ICAP)"


def _has_builtin_av(low: str) -> bool:
    """«Встроенный антивирус» в любом падеже: основа «встроенн» + «антивирус»."""
    return "антивирус" in low and "встроенн" in low


def detect_unsupported(text: str) -> list[str]:
    """Возвращает список найденных неподдерживаемых потребностей (описания)."""
    low = text.lower()
    found: list[str] = []
    if _has_builtin_av(low):
        found.append(_BUILTIN_AV_DESC)
    for marker, desc in KNOWN_UNSUPPORTED:
        if marker in low and desc not in found:
            found.append(desc)
    return found


class VendorRequests:
    """Коллектор потребностей для разработчика. Один на сессию."""

    def __init__(self, session_id: str = "") -> None:
        self.session_id = session_id
        self._items: list[dict[str, Any]] = []

    def add(self, text: str, *, kind: str = "unsupported", turn_id: int = 0) -> None:
        """kind: 'unsupported' | 'other'."""
        if not text or not text.strip():
            return
        self._items.append(
            {
                "kind": kind,
                "text": text.strip(),
                "turn_id": turn_id,
            }
        )

    def scan(self, text: str, *, turn_id: int = 0) -> list[str]:
        """Находит неподдерживаемое в тексте и добавляет. Возвращает найденное."""
        found = detect_unsupported(text)
        for desc in found:
            self.add(desc, kind="unsupported", turn_id=turn_id)
        return found

    def items(self) -> list[dict[str, Any]]:
        return list(self._items)

    def to_list(self) -> list[str]:
        """Плоский список строк для поля requests_for_vendor."""
        return [i["text"] for i in self._items]
