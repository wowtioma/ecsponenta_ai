"""Формирование человеческих ответов и фактов (участок B).

Здесь собираются тексты, которые видит пользователь: объяснение размещения,
объяснение правил, ответы на фактические вопросы о продукте (с цитатами).
Числа правил и размещение считает A (core), сюда приходят уже готовые структуры.
"""
from __future__ import annotations

from . import prompts, rag
from .client import LLMClient

# Русские подписи режимов и типов для текста.
MODE_RU = {"one-way": "однонаправленное", "two-way": "двунаправленное"}
TYPE_RU = {"data": "данные", "file": "файлы"}


def explain_placement(cfg: dict) -> str:
    """Текст о размещении Синоникса и МЭ (методика §2)."""
    syn = cfg.get("synonyx", {})
    fw = cfg.get("firewall", {})
    location = syn.get("location", "closed")
    side = fw.get("side", "open")
    lines = [
        "Межсетевой экран размещается на границе защищаемого (закрытого) сегмента "
        "со стороны открытой сети. «Синоникс» находится внутри закрытого сегмента "
        "сразу за межсетевым экраном.",
        "Узел А обращён к открытой сети, Узел В — к системам закрытого сегмента, "
        "Ядро — между ними.",
    ]
    if side == "both":
        lines.append("Обе сети открытые, поэтому межсетевые экраны стоят с двух сторон.")
    return "\n".join(lines)


def explain_rules(rules: list[dict], networks=()) -> str:
    """Explain calculated rules using the same parameters shown in the table."""
    if not rules:
        return "Правил Синоникса: 0."
    names = {"open": "Открытая сеть", "closed": "Закрытый сегмент",
             "node_a": "Узел А", "node_b": "Узел В"}
    names.update({network["id"]: network["name"] for network in networks})
    lines = [f"Правил Синоникса: {len(rules)}.", ""]
    for rule in rules:
        mode = MODE_RU.get(rule.get("mode", ""), rule.get("mode", ""))
        protocol = rule.get("protocol")
        desc = rule.get("description") or "Передача"
        if rule.get("type") == "file":
            if isinstance(protocol, dict):
                methods = "; ".join(f"{names.get(side, side)} — {label}"
                                    for side, label in protocol.items() if label)
            else:
                methods = protocol or ("USB-носитель на Узле А" if rule.get("transport") == "usb" else "")
            text = f"{desc}. {mode.capitalize()} файловое правило."
            if methods:
                text += f" Способы передачи: {methods}."
            checks = rule.get("checks_by_node")
            if isinstance(checks, dict) and checks:
                text += " Проверки: " + "; ".join(
                    f"{names.get(side, side)} — {', '.join(items) if items else 'без проверок'}"
                    for side, items in checks.items()
                ) + "."
            elif rule.get("checks"):
                text += " Проверки: " + ", ".join(rule["checks"]) + "."
            lines.append(f"{rule.get('id', '')}. {text}")
            continue
        port = rule.get("port")
        params = protocol or "протокол не указан"
        if port is not None:
            params = f"{params} {port}"
        lines.append(f"{rule.get('id', '')}. {desc}: {params}, {mode} правило.")
    return "\n".join(lines)


def _context_block(hits: list[dict]) -> str:
    parts = []
    for h in hits:
        parts.append(f"[{h['file']} | {h['section']}]\n{h['text']}")
    return "\n\n".join(parts)


def answer_fact(
    client: LLMClient | None,
    query: str,
    *,
    kb: rag.KnowledgeBase | None = None,
    session_id: str = "",
    turn_id: int = 0,
) -> tuple[str, list[dict]]:
    """Фактический ответ о продукте. Возвращает (текст, найденные фрагменты).

    Без LLM (client=None) возвращает найденные фрагменты с цитатами — этого
    достаточно для офлайн-проверки и для Q01/Q10, где факт уже есть в базе.
    """
    kb = kb or rag.get_kb()
    hits = kb.search(query, top_k=3)
    if not hits:
        return ("В базе знаний не нашлось подтверждённого ответа на этот вопрос.", [])
    if client is None:
        cite = kb.cite(hits[0])
        text = hits[0]["text"]
        return (f"{text}\n\nИсточник: {cite}.", hits)

    reply, _rec = client.chat(
        [
            {"role": "system", "content": prompts.SYSTEM_FACT},
            {"role": "user", "content": f"Вопрос: {query}\n\nКонтекст:\n{_context_block(hits)}"},
        ],
        purpose="fact",
        session_id=session_id,
        turn_id=turn_id,
        temperature=0.0,
        max_tokens=1024,
    )
    if not reply.strip():
        return hits[0]["text"], hits
    return reply, hits
