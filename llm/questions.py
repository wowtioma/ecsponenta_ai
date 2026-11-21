"""Генерация формулировок уточняющих вопросов (участок B).

Разделение ответственности:
  - участок A определяет, ЧЕГО не хватает (детерминированно, по своей модели)
    и отдаёт список вопросов с id и вариантами ответа;
  - участок B формулирует, КАК спросить: живо, по словам пользователя, без
    повторов того, что уже сказано.

id и варианты ответа B не меняет — по id участок A применяет ответы
(apply_answer), поэтому переформулировка безопасна.

Если LLM недоступна, возвращаются исходные вопросы участка A.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from . import prompts
from .client import LLMClient
from .extract import _parse_json_lenient

logger = logging.getLogger("llm.questions")

# ТЗ §3.2: у каждого вопроса есть варианты ответа, «не знаю» и «другое».
REQUIRED_OPTIONS = ("Не знаю", "Другое")


def ensure_options(question: dict) -> dict:
    """Дополняет варианты ответа обязательными «Не знаю» и «Другое»."""
    options = [str(o) for o in (question.get("options") or [])]
    present = {o.strip().casefold() for o in options}
    for tail in REQUIRED_OPTIONS:
        if tail.casefold() not in present:
            options.append(tail)
    question["options"] = options
    return question


def rephrase_questions(
    client: LLMClient | None,
    questions: list[dict] | None,
    user_text: str = "",
    *,
    session_id: str = "",
    turn_id: int = 0,
) -> list[dict]:
    """Переформулирует уточняющие вопросы участка A.

    Возвращает список той же длины и с теми же id; меняется только текст.
    При любой ошибке LLM — исходные тексты A.
    """
    items: list[dict] = [dict(q) for q in (questions or []) if isinstance(q, dict)]
    if not items:
        return []
    for q in items:
        ensure_options(q)

    if client is None:
        return items

    payload = {
        "user_text": user_text,
        "questions": [
            {"id": q.get("id"), "text": q.get("text"), "options": q.get("options")}
            for q in items
        ],
    }
    try:
        reply, _rec = client.chat(
            [
                {"role": "system", "content": prompts.SYSTEM_QUESTIONS},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            purpose="questions",
            session_id=session_id,
            turn_id=turn_id,
            temperature=0.0,
            max_tokens=2000,
        )
        data = _parse_json_lenient(reply)
        by_id: dict[str, Any] = {}
        for q in data.get("questions") or []:
            if isinstance(q, dict) and q.get("id") is not None:
                by_id[str(q["id"])] = q

        for q in items:
            replacement = by_id.get(str(q.get("id")))
            if not isinstance(replacement, dict):
                continue
            text = replacement.get("text")
            if isinstance(text, str) and text.strip():
                q["text"] = text.strip()
    except Exception as exc:  # noqa: BLE001
        # Сбой LLM не должен ломать диалог: отдаём вопросы A как есть.
        logger.warning("rephrase_questions fallback: %s", exc)

    return items
