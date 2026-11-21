"""Сохранение журнала сессии на диск (ТЗ §8).

Журнал должен сохраняться на время проверки и выгружаться в JSON/JSONL либо CSV.
Пишем:
  - sessions/<session_id>.jsonl  — по одной строке на вызов модели;
  - sessions/<session_id>.json   — сводка сессии (стоимость, модели, тайминги).

Каталог sessions/ лежит в корне проекта и не трогается venv/.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config, report
from .journal import Journal


def sessions_dir() -> Path:
    return Path(config.ROOT / "sessions")


def save_session(
    journal: Journal,
    session_id: str,
    *,
    data_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Сохраняет журнал сессии на диск. Возвращает пути к файлам."""
    d = data_dir or sessions_dir()
    d.mkdir(parents=True, exist_ok=True)

    # 1. JSONL — полный журнал вызовов (по строке на вызов).
    jsonl_path = d / f"{session_id}.jsonl"
    jsonl_path.write_text(
        journal.export_jsonl(session_id) + ("\n" if journal.calls(session_id) else ""),
        encoding="utf-8",
    )

    # 2. JSON — сводка сессии + расходы + тайминги (совместимо с result.example.json).
    summary = {
        "session_id": session_id,
        "cost_total_usd": journal.session_cost(session_id),
        "models": journal.model_breakdown(session_id),
        "usage": report.build_usage(journal, session_id),
        "timing": report.build_timing(journal, session_id),
    }
    if extra:
        summary["extra"] = extra
    json_path = d / f"{session_id}.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"jsonl": str(jsonl_path), "json": str(json_path)}


def load_session(session_id: str, *, data_dir: Path | None = None) -> dict[str, Any]:
    """Читает сохранённую сводку сессии. Падает, если файла нет."""
    d = data_dir or sessions_dir()
    p = d / f"{session_id}.json"
    return json.loads(p.read_text(encoding="utf-8"))
