#!/usr/bin/env python
"""Проверка Yandex AI Studio: какая модель реально доступна в твоём каталоге.

Запуск (из корня проекта, после заполнения .env):
    python check_yandex.py

Скрипт по очереди пробует самые дешёвые модели AI Studio, которые есть
в каталоге OpenRouter (gpt-oss-20b -> gpt-oss-120b -> qwen3-235b),
делает минимальный запрос и печатает результат + стоимость по каталогу.
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

# Порядок перебора: от самой дешёвой к самой дорогой.
CANDIDATES = ["gpt-oss-20b", "gpt-oss-120b", "qwen3-235b-a22b-fp8"]


def main() -> int:
    if not config.YANDEX_API_KEY:
        print("YANDEX_API_KEY не задан в .env")
        return 1
    if not config.YANDEX_FOLDER_ID:
        print("YANDEX_FOLDER_ID не задан в .env")
        return 1

    folder = config.YANDEX_FOLDER_ID
    print(f"Каталог: {folder}")
    print(f"Endpoint: {config.YANDEX_BASE_URL}")
    print("Перебор моделей...\n")

    for name in CANDIDATES:
        journal = Journal()
        client = LLMClient(
            journal,
            api_key=config.YANDEX_API_KEY,
            model=f"gpt://{folder}/{name}",
            base_url=config.YANDEX_BASE_URL,
        )
        print(f"→ {name} ...", end=" ", flush=True)
        try:
            text, rec = client.chat(
                [{"role": "user", "content": "Ответь одним словом: работает?"}],
                purpose="probe",
                session_id="probe",
                turn_id=1,
                max_tokens=32,
            )
            print("OK")
            print(f"   ответ: {text.strip()[:80]!r}")
            print(f"   токены: in={rec.input_tokens} out={rec.output_tokens}")
            print(f"   в журнал как: {rec.model_id}")
            print(f"   стоимость по каталогу OpenRouter: ${rec.cost_total:.8f}")
            cat, p_in, p_out = config.billable_tariff(f"gpt://{folder}/{name}")
            print(f"   тариф: ${p_in}/${p_out} за 1M (каталог: {cat})")
            print(f"   вход <= $0.10: {'ДА' if p_in <= config.PRICE_LIMIT_INPUT else 'НЕТ'}")

            # Дозаписываем в .env рекомендованную модель.
            print(f"\nРЕКОМЕНДАЦИЯ: YANDEX_MODEL={name}")
            print("Впиши это в .env и поставь LLM_PROVIDER=yandex")
            return 0
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            short = msg.split("\n")[0][:160]
            print(f"недоступна — {short}")

    print("\nНи одна из моделей не ответила. Проверь:")
    print(" - роль сервисного аккаунта: ai.languageModels.user")
    print(" - API-ключ создан в этом же каталоге")
    print(" - грант активен (Billing -> Гранты)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
