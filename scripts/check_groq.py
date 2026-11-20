#!/usr/bin/env python
"""Проверка ключа Groq: показывает доступные модели и тестирует gpt-oss.

Запуск:
    python check_groq.py
    python check_groq.py openai/gpt-oss-120b
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import json
import sys
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from llm import Journal, LLMClient, config  # noqa: E402


def list_models(api_key: str) -> list[dict]:
    req = urllib.request.Request(
        f"{config.GROQ_BASE_URL}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8")).get("data", [])


def main() -> int:
    if not config.GROQ_API_KEY:
        print("GROQ_API_KEY не задан в .env")
        return 1

    print(f"Endpoint: {config.GROQ_BASE_URL}\n")

    # 1. Какие модели реально доступны ключу
    try:
        models = list_models(config.GROQ_API_KEY)
    except Exception as exc:  # noqa: BLE001
        print(f"Не удалось получить список моделей: {str(exc)[:200]}")
        models = []

    if models:
        print(f"Доступные модели ({len(models)}):")
        for m in models:
            mid = m.get("id", "?")
            ctx = m.get("context_window") or ""
            mark = " ← нужна нам" if "gpt-oss" in mid else ""
            print(f"  - {mid:45s} ctx={ctx}{mark}")
        print()

    # 2. Тестируем выбранную модель
    model = sys.argv[1] if len(sys.argv) > 1 else config.GROQ_MODEL
    print(f"Тест модели: {model}")
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
        if "429" in msg:
            print("Лимит бесплатного плана. Подожди или смени модель.")
        elif "401" in msg:
            print("Ключ неверный. Проверь GROQ_API_KEY в .env")
        elif "404" in msg or "model" in msg.lower():
            print("Модель недоступна. Возьми id из списка выше.")
        return 1

    cat, p_in, p_out = config.billable_tariff(model)
    print("OK")
    print(f"  ответ: {text.strip()[:120]!r}")
    print(f"  токены: in={rec.input_tokens} out={rec.output_tokens}")
    print(f"  в журнал как: {rec.model_id}  (каталог OpenRouter)")
    print(f"  тариф по каталогу: ${p_in}/${p_out} за 1M")
    print(f"  вход <= ${config.PRICE_LIMIT_INPUT}: {'ДА' if p_in <= config.PRICE_LIMIT_INPUT else 'НЕТ'}")
    print(f"  стоимость: ${rec.cost_total:.8f}")
    return 0 if p_in <= config.PRICE_LIMIT_INPUT else 2


if __name__ == "__main__":
    sys.exit(main())
