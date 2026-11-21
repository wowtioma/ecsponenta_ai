#!/usr/bin/env python
"""Извлекает слоты из сценария F02 (04_benchmarks.json) и сохраняет в f02_slots.json.

Нужно участнику A для интеграции: файл содержит ровно тот dict, который вернул
extract() — без изменений.

Запуск (из корня проекта, ключ в .env):
    python scripts/dump_f02.py
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import json
from pathlib import Path

from llm import Journal, LLMClient, config, extract

BENCH = Path(config.ROOT) / "Кейс АйТи Бастион — Синоникс" / "synonyx_base" / "04_benchmarks.json"
OUT = Path(config.ROOT) / "f02_slots.json"


def main() -> int:
    items = json.loads(BENCH.read_text(encoding="utf-8"))["items"]
    item = next(i for i in items if i["id"] == "F02")
    query = item["query"]

    journal = Journal()
    client = LLMClient(journal)
    res = extract(client, query, session_id="f02", turn_id=1)

    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\nСохранено: {OUT}")
    print(f"Стоимость извлечения: ${journal.session_cost('f02'):.8f}")
    if res.get("_fallback"):
        print("!!! СРАБОТАЛ ФОЛБЭК:", res.get("_warning"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
