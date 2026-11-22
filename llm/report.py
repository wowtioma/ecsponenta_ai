"""Отчёт usage/timing по схеме result.example.json (ТЗ §8, §9, §10).

Служебный JSON результата содержит поля usage и timing — их заполняет участник B
из журнала. Точный состав см. в result.example.json кейса.
"""
from __future__ import annotations

from typing import Any

from .journal import Journal


def build_usage(journal: Journal, session_id: str) -> dict[str, Any]:
    """Блок usage по схеме кейса: токены, стоимость (оценочная и фактическая), calls."""
    calls = journal.calls(session_id)
    measured = [call for call in calls if call.cost_source != "unknown"]
    if not measured:
        return {
            "status": "not_measured",
            "input_tokens": None,
            "output_tokens": None,
            "input_cost_usd": None,
            "output_cost_usd": None,
            "evaluation_cost_usd": None,
            "actual_cost_usd": None,
            "calls": [_call_dict(call) for call in calls],
        }

    input_tokens = sum(r.input_tokens for r in measured)
    output_tokens = sum(r.output_tokens for r in measured)
    cost_input = sum(r.cost_input for r in measured)
    cost_output = sum(r.cost_output for r in measured)
    cost_total = sum(r.cost_total for r in measured)

    # Фактическая стоимость — только те вызовы, где провайдер вернул usage.cost.
    provider_calls = [r for r in calls if r.cost_source == "provider"]
    actual = sum(r.cost_total for r in provider_calls) if provider_calls else None

    return {
        "status": "measured" if len(measured) == len(calls) else "partial",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost_usd": cost_input,
        "output_cost_usd": cost_output,
        # Оценочная стоимость по снимку тарифов OpenRouter (ТЗ §8).
        "evaluation_cost_usd": cost_total,
        # Фактическая из usage.cost провайдера, если он её вернул.
        "actual_cost_usd": actual,
        "calls": [_call_dict(r) for r in calls],
    }


def _call_dict(r) -> dict[str, Any]:
    """Одна запись в usage.calls — соответствует требованиям ТЗ §8."""
    return {
        "session_id": r.session_id,
        "turn_id": r.turn_id,
        "call_id": r.call_id,
        "model_id": r.model_id,
        "provider_variant": r.provider_variant,
        "purpose": r.purpose,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "status": r.status,
        "input_tokens": r.input_tokens if r.cost_source != "unknown" else None,
        "output_tokens": r.output_tokens if r.cost_source != "unknown" else None,
        "cached_tokens": r.cached_tokens,
        "reasoning_tokens": r.reasoning_tokens,
        "prompt_price": r.prompt_price,
        "completion_price": r.completion_price,
        "cost_input_usd": r.cost_input if r.cost_source != "unknown" else None,
        "cost_output_usd": r.cost_output if r.cost_source != "unknown" else None,
        "cost_total_usd": r.cost_total if r.cost_source != "unknown" else None,
        "cost_source": r.cost_source,
        "provider_response_id": r.provider_response_id,
    }


def build_timing(journal: Journal, session_id: str) -> dict[str, Any]:
    """Блок timing: turns[] и mean_turn_seconds.

    Время шага измеряется как (последний finished_at — первый started_at) среди
    вызовов одного turn_id. Это модельное время; полное время «вопрос -> готовый
    ответ с рендером» фиксирует слой приложения (участок C).
    """
    calls = journal.calls(session_id)
    turns: list[dict[str, Any]] = []
    by_turn: dict[int, list] = {}
    for r in calls:
        by_turn.setdefault(r.turn_id, []).append(r)

    durations = []
    for turn_id in sorted(by_turn):
        rs = by_turn[turn_id]
        start = min(r.started_at for r in rs)
        end = max((r.finished_at or r.started_at) for r in rs)
        seconds = round(end - start, 3)
        durations.append(seconds)
        turns.append(
            {
                "turn_id": turn_id,
                "seconds": seconds,
                "calls": len(rs),
                "call_ids": [r.call_id for r in rs],
            }
        )

    mean = round(sum(durations) / len(durations), 3) if durations else None
    return {"turns": turns, "mean_turn_seconds": mean}
