#!/usr/bin/env python
"""Демонстрация полной сессии участка B.

Показывает три вещи в одном прогоне:
  1) извлечение слотов из свободного текста;
  2) ответ на вопрос о продукте строго по базе знаний (с цитатой);
  3) полный финансовый учёт: журнал вызовов, токены, стоимость, usage/timing.

Запуск (из корня проекта, ключ в .env):
    python scripts/demo_session.py
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import json
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from llm import (  # noqa: E402
    Journal,
    LLMClient,
    answer_fact,
    build_timing,
    build_usage,
    config,
    extract,
    save_session,
)

TEXT = (
    "Насосная станция водоканала в отдельной закрытой сети. Диспетчер в общей сети. "
    "Программа диспетчера опрашивает контроллер насосов по Modbus TCP, порт 502. "
    "Компьютер оператора станции отправляет журналы на сервер мониторинга в общей сети "
    "по UDP 514, обратно ничего. Сервер времени общей сети передаёт время станции по NTP, UDP 123."
)
QUESTION = "Сколько правил можно настроить на одном Синониксе?"


def main() -> int:
    _base, model, key = config.resolve_endpoint()
    print(f"provider={config.active_provider()}  model={model}")
    if not key or "ВСТАВЬ" in key:
        print("Ключ не задан в .env")
        return 1

    session_id = "demo-session"
    journal = Journal()
    client = LLMClient(journal)

    # 1. Извлечение слотов
    print("\n=== 1. ИЗВЛЕЧЕНИЕ СЛОТОВ ===")
    res = extract(client, TEXT, session_id=session_id, turn_id=1)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res.get("_fallback"):
        print("!!! СРАБОТАЛ ФОЛБЭК:", res.get("_warning"))

    # 2. Факт по базе знаний
    print("\n=== 2. ФАКТ ПО БАЗЕ ЗНАНИЙ ===")
    ans, hits = answer_fact(client, QUESTION, session_id=session_id, turn_id=2)
    print(ans.strip())
    if hits:
        print(f"Источник: {hits[0]['file']}, раздел «{hits[0]['section']}»")

    # 3. Финансовый учёт
    print("\n=== 3. ФИНАНСОВЫЙ УЧЁТ СЕССИИ ===")
    print(f"{'назначение':12s} {'in':>6s} {'out':>6s} {'стоимость':>13s}")
    for c in journal.calls(session_id):
        print(f"{c.purpose:12s} {c.input_tokens:6d} {c.output_tokens:6d} ${c.cost_total:.8f}")
    print(f"{'ИТОГО':12s} {sum(c.input_tokens for c in journal.calls(session_id)):6d} "
          f"{sum(c.output_tokens for c in journal.calls(session_id)):6d} "
          f"${journal.session_cost(session_id):.8f}")

    usage = build_usage(journal, session_id)
    timing = build_timing(journal, session_id)
    print("\nusage:", json.dumps({k: v for k, v in usage.items() if k != "calls"}, ensure_ascii=False))
    print("timing:", json.dumps(timing, ensure_ascii=False))

    # 4. Сохранение журнала
    paths = save_session(journal, session_id)
    print("\n=== 4. ЖУРНАЛ СОХРАНЁН ===")
    for k, v in paths.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
