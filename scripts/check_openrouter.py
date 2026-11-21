#!/usr/bin/env python
"""Проверка рабочего ключа OpenRouter и бесплатной модели Grok.

Запуск:
    python check_openrouter.py
    python check_openrouter.py x-ai/grok-4.1-fast:free
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from llm import Journal, LLMClient, config  # noqa: E402


def main() -> int:
    if not config.OPENROUTER_API_KEY:
        print("OPENROUTER_API_KEY не задан в .env")
        return 1

    model = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_MODEL
    print(f"Endpoint: {config.OPENROUTER_BASE_URL}")
    print(f"Модель:   {model}\n")

    journal = Journal()
    client = LLMClient(journal, model=model)

    try:
        text, rec = client.chat(
            [{"role": "user", "content": "Ответь одним словом: работает?"}],
            purpose="probe",
            session_id="probe",
            turn_id=1,
            max_tokens=32,
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        print(f"ОШИБКА: {msg.split(chr(10))[0][:300]}")
        low = msg.lower()
        if "429" in msg or "rate limit" in low:
            print("\nЭто лимит бесплатных моделей: 50 запросов в день, 20 в минуту.")
            print("Подожди до следующего дня (UTC) или купи $10 кредитов -> 1000/день.")
        elif "401" in msg or "unauthorized" in low:
            print("\nКлюч неверный или отозван. Проверь OPENROUTER_API_KEY в .env")
        elif "404" in msg or "not found" in low:
            print("\nМодель недоступна. Проверь id на openrouter.ai/models")
        return 1

    print("OK")
    print(f"  ответ: {text.strip()[:120]!r}")
    print(f"  токены: in={rec.input_tokens} out={rec.output_tokens}")
    print(f"  стоимость: ${rec.cost_total:.8f} (source={rec.cost_source})")
    _, p_in, p_out = config.billable_tariff(model)
    print(f"  тариф модели: ${p_in}/${p_out} за 1M")
    ok = p_in <= config.PRICE_LIMIT_INPUT
    print(f"  вход <= ${config.PRICE_LIMIT_INPUT}: {'ДА' if ok else 'НЕТ'}")
    print(f"  provider_response_id: {rec.provider_response_id}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
