"""Журнал модельных вызовов и учёт стоимости сессии (ТЗ §8).

Один CallRecord = один вызов модели. Журнал хранит вызовы по call_id и не
допускает повторного учёта одного call_id (защита от удвоения расходов).
"""
from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass, field
from typing import Any

from . import config


@dataclass
class CallRecord:
    session_id: str
    turn_id: int
    call_id: str
    model_id: str
    purpose: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    prompt_price: float = 0.0          # USD/1M вход
    completion_price: float = 0.0      # USD/1M выход
    cost_input: float = 0.0
    cost_output: float = 0.0
    cost_total: float = 0.0
    cost_source: str = "estimated"     # "provider" | "estimated" | "unknown"
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    status: str = "ok"
    provider_variant: str = ""
    provider_response_id: str = ""
    raw_usage: Any = None              # исходный usage провайдера (как есть)

    def to_dict(self) -> dict:
        d = {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "call_id": self.call_id,
            "model_id": self.model_id,
            "purpose": self.purpose,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "prompt_price": self.prompt_price,
            "completion_price": self.completion_price,
            "cost_input": self.cost_input,
            "cost_output": self.cost_output,
            "cost_total": self.cost_total,
            "cost_source": self.cost_source,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "provider_variant": self.provider_variant,
            "provider_response_id": self.provider_response_id,
            "raw_usage": self.raw_usage,
        }
        return d


class Journal:
    """Журнал вызовов. Один журнал на процесс (сервер); внутри — много сессий."""

    def __init__(self) -> None:
        self._by_call: dict[str, CallRecord] = {}

    def add(self, rec: CallRecord) -> bool:
        """Добавляет запись. Возвращает False, если call_id уже учтён (не дублирует)."""
        if rec.call_id in self._by_call:
            return False
        self._by_call[rec.call_id] = rec
        return True

    def calls(self, session_id: str | None = None) -> list[CallRecord]:
        recs = list(self._by_call.values())
        recs.sort(key=lambda r: r.started_at)
        if session_id is not None:
            recs = [r for r in recs if r.session_id == session_id]
        return recs

    def session_cost(self, session_id: str) -> float:
        """Сумма оценочных стоимостей всех вызовов сессии (ТЗ §8)."""
        return sum(r.cost_total for r in self.calls(session_id))

    def model_breakdown(self, session_id: str) -> dict[str, dict]:
        """Разбивка по моделям: вызовы, токены входа/выхода, стоимость."""
        out: dict[str, dict] = {}
        for r in self.calls(session_id):
            m = out.setdefault(
                r.model_id,
                {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_total": 0.0},
            )
            m["calls"] += 1
            m["input_tokens"] += r.input_tokens
            m["output_tokens"] += r.output_tokens
            m["cost_total"] += r.cost_total
        return out

    def export_jsonl(self, session_id: str | None = None) -> str:
        return "\n".join(
            json.dumps(r.to_dict(), ensure_ascii=False)
            for r in self.calls(session_id)
        )

    def export_csv(self, session_id: str | None = None) -> str:
        buf = io.StringIO()
        fields = [
            "session_id", "turn_id", "call_id", "model_id", "purpose",
            "input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens",
            "prompt_price", "completion_price", "cost_input", "cost_output",
            "cost_total", "cost_source", "status", "provider_response_id",
        ]
        w = csv.DictWriter(buf, fieldnames=fields)
        w.writeheader()
        for r in self.calls(session_id):
            w.writerow({k: r.to_dict().get(k, "") for k in fields})
        return buf.getvalue()
