#!/usr/bin/env python
"""Демо-скрипт участника B: проверь свою часть без запуска всего приложения.

Примеры (из корня проекта, venv активирован):
    python demo_b.py starter
    python demo_b.py fact "Сколько правил можно настроить на одном Синониксе?"
    python demo_b.py extract "Насосная станция — закрытая сеть. Диспетчер в общей сети опрашивает контроллер по Modbus TCP 502."

`fact` и `starter` работают без ключа OpenRouter. `extract` использует LLM, если
задан OPENROUTER_API_KEY, иначе падает в regex-фолбэк.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import argparse
import json
import sys

# Консоль Windows по умолчанию cp1251 и падает на юникоде — форсируем UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from llm import (
    Journal,
    LLMClient,
    answer_fact,
    extract,
    get_kb,
    prompts,
    config,
)


def cmd_starter() -> int:
    print(prompts.STARTER_MESSAGE)
    return 0


def cmd_fact(query: str) -> int:
    client = None
    _base, _model, api_key = config.resolve_endpoint()
    if api_key and "ВСТАВЬ" not in api_key:
        client = LLMClient(Journal())
    text, hits = answer_fact(client, query)
    print(text)
    if hits:
        print("\n--- найденные фрагменты ---")
        for h in hits:
            print(f"[{h['file']} | {h['section']}] score={h['score']}")
    return 0


def cmd_extract(text: str) -> int:
    journal = Journal()
    # use_llm определяем по активному профилю, а не только по OpenRouter.
    _base, _model, api_key = config.resolve_endpoint()
    use_llm = bool(api_key) and "ВСТАВЬ" not in api_key
    client = LLMClient(journal) if use_llm else LLMClient(journal, api_key="")
    result = extract(client, text, session_id="demo", turn_id=1, use_llm=use_llm)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n[provider={config.active_provider()}, model={config.resolve_endpoint()[:2][1]}]")
    if use_llm and journal.calls():
        print(f"Стоимость сессии: ${journal.session_cost('demo'):.8f}")
        print(f"Время: {journal.calls()[-1].finished_at - journal.calls()[0].started_at:.2f} сек")
    return 0


def cmd_models() -> int:
    for m, (p_in, p_out) in config.MODEL_TARIFFS.items():
        ok = p_in <= config.PRICE_LIMIT_INPUT
        print(f"{m:40s} in=${p_in:<6} out=${p_out:<6} {'OK' if ok else 'ПРЕВЫШАЕТ ЛИМИТ'}")
    print(f"\nМодель по умолчанию: {config.DEFAULT_MODEL}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Демо участника B")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("starter")
    f = sub.add_parser("fact")
    f.add_argument("query")
    e = sub.add_parser("extract")
    e.add_argument("text")
    sub.add_parser("models")

    args = p.parse_args()
    if args.cmd == "starter":
        return cmd_starter()
    if args.cmd == "fact":
        return cmd_fact(args.query)
    if args.cmd == "extract":
        return cmd_extract(args.text)
    if args.cmd == "models":
        return cmd_models()
    return 1


if __name__ == "__main__":
    sys.exit(main())
