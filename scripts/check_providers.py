#!/usr/bin/env python
"""Проверка провайдеров модели через OpenRouter API (ТЗ §7).

Показывает ВСЕХ провайдеров модели с ценами — включая скрытые в UI — и отмечает,
кто проходит лимит входного тарифа $0.10/1M, а кто нет.

Запуск (из корня проекта):
    python check_providers.py
    python check_providers.py meta-llama/llama-3.3-70b-instruct
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import json
import sys
import urllib.request

from llm import config


def fetch_endpoints(model: str) -> list[dict]:
    url = f"{config.OPENROUTER_BASE_URL}/models/{model}/endpoints"
    req = urllib.request.Request(url)
    if config.OPENROUTER_API_KEY:
        req.add_header("Authorization", f"Bearer {config.OPENROUTER_API_KEY}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("data", {}).get("endpoints", [])


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_MODEL
    print(f"Модель: {model}")
    print(f"Лимит входного тарифа: ${config.PRICE_LIMIT_INPUT}/1M\n")

    try:
        endpoints = fetch_endpoints(model)
    except Exception as exc:  # noqa: BLE001
        print(f"Не удалось получить endpoints: {exc}")
        print("Проверь сеть/ключ. Показываю локально заявленный тариф:")
        try:
            p_in, p_out = config.tariff(model)
            print(f"  заявлено: in=${p_in} out=${p_out}")
        except KeyError as e:
            print(f"  {e}")
        return 1

    if not endpoints:
        print("Провайдеры не найдены.")
        return 1

    rows = []
    for ep in endpoints:
        price = ep.get("pricing", {})
        # pricing.prompt/completion — строки в USD ЗА ТОКЕН
        p_in = float(price.get("prompt", 0) or 0) * 1_000_000
        p_out = float(price.get("completion", 0) or 0) * 1_000_000
        rows.append(
            {
                "name": ep.get("provider_name") or ep.get("name", "?"),
                "tag": ep.get("tag", ""),
                "p_in": p_in,
                "p_out": p_out,
                "ctx": ep.get("context_length"),
                "uptime": ep.get("uptime_last_30m"),
            }
        )

    rows.sort(key=lambda r: r["p_in"])
    print(f"{'Провайдер':28s} {'Вход/1M':>9s} {'Выход/1M':>9s} {'Uptime':>8s}  Вердикт")
    print("-" * 78)
    ok_list = []
    for r in rows:
        ok = r["p_in"] <= config.PRICE_LIMIT_INPUT + 1e-9
        verdict = "OK" if ok else "ПРЕВЫШАЕТ"
        if ok:
            ok_list.append(r)
        name = f"{r['name']} ({r['tag']})" if r["tag"] else r["name"]
        up = f"{r['uptime']:.1f}%" if isinstance(r["uptime"], (int, float)) else "-"
        print(f"{name[:28]:28s} ${r['p_in']:>8.4f} ${r['p_out']:>8.4f} {up:>8s}  {verdict}")

    print()
    if ok_list:
        cheapest = ok_list[0]
        print(f"Самый дешёвый допущенный: {cheapest['name']} ({cheapest['tag']}) "
              f"${cheapest['p_in']:.4f}/${cheapest['p_out']:.4f}")
        routing = config.provider_routing(model)
        if routing:
            print(f"В config привязано: {routing}")
            pinned = routing.get("only", [])
            if pinned:
                found = any(pinned[0].lower() in (cheapest["name"] or "").lower()
                            or pinned[0].lower() in (cheapest["tag"] or "").lower()
                            for _ in [0])
                if not found:
                    print(f"ВНИМАНИЕ: привязан {pinned}, а самый дешёвый — "
                          f"{cheapest['name']}. Проверь MODEL_PROVIDER в config.py.")
    else:
        print("НЕТ допущенных провайдеров: у всех вход выше лимита. Модель нельзя брать.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
