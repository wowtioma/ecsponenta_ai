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


def explain_rules(rules: list[dict]) -> str:
    """Текст «Правил Синоникса: N» + по одной строке на правило (методика §6.5)."""
    if not rules:
        return "Правил Синоникса: 0."
    out = [f"Правил Синоникса: {len(rules)}."]
    for r in rules:
        mode = MODE_RU.get(r.get("mode", ""), r.get("mode", ""))
        proto = r.get("protocol", "")
        port = r.get("port")
        proto_str = f"{proto} {port}" if port is not None else str(proto)
        desc = r.get("description", "")
        out.append(f"{r.get('id', '')}. {desc}: {proto_str}, {mode} правило.")
    return "\n".join(out)


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
        max_tokens=512,
    )
    return reply, hits
