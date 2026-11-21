#!/usr/bin/env python
"""Прогон участка B на всех открытых бенчмарках (04_benchmarks.json).

Покрытие по группам:
  full/basic     — extract(): сверка data-правил (protocol/port/from/to/mode);
  facts          — answer_fact(): ответ содержит ключевой факт + цитату из базы;
  out_of_scope   — vendor.detect_unsupported(): найдена потребность для разработчика;
  incomplete     — пропускается (уточняющие вопросы — зона участка A).

Запуск (нужен ключ провайдера в .env):
    python benchmark_test.py
    python benchmark_test.py F02
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from llm import (  # noqa: E402
    Journal,
    LLMClient,
    answer_fact,
    config,
    detect_unsupported,
    extract,
    get_kb,
)

BENCH_PATH = Path(config.ROOT) / "Кейс АйТи Бастион — Синоникс" / "synonyx_base" / "04_benchmarks.json"

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️"

# Ключевые подстроки для фактических сценариев (проверяем ответ по базе знаний).
FACTS_MUST_CONTAIN = {
    "Q01": ["256"],
    "Q10": ["межсетевой", "защит"],
}


def normalize(p):
    return int(p) if p is not None else None


def match_data_rule(flow: dict, rule: dict) -> list[str]:
    diffs = []
    if flow.get("protocol") != rule.get("protocol"):
        diffs.append(f"protocol {flow.get('protocol')} != {rule.get('protocol')}")
    if normalize(flow.get("port")) != rule.get("port"):
        diffs.append(f"port {flow.get('port')} != {rule.get('port')}")
    if flow.get("from") != rule.get("from"):
        diffs.append(f"from {flow.get('from')} != {rule.get('from')}")
    if flow.get("to") != rule.get("to"):
        diffs.append(f"to {flow.get('to')} != {rule.get('to')}")
    if flow.get("mode") != rule.get("mode"):
        diffs.append(f"mode {flow.get('mode')} != {rule.get('mode')}")
    return diffs


def check_project(item: dict, client: LLMClient, session_id: str) -> dict:
    expected = item.get("expected") or {}
    rules = expected.get("rules", [])
    res = extract(client, item["query"], session_id=session_id, turn_id=1)
    if res.get("_fallback"):
        return {"ok": False, "detail": res.get("_warning", "fallback")}
    flows = res.get("flows", [])
    results = []
    for rule in rules:
        if rule.get("type") != "data":
            has_file = any(f.get("type") == "file" for f in flows)
            results.append((f"file {rule.get('description','')[:24]}", has_file, []))
            continue
        cand = [f for f in flows if f.get("protocol") == rule.get("protocol")
                and normalize(f.get("port")) == rule.get("port")]
        if not cand:
            results.append((f"data {rule.get('protocol')} {rule.get('port')}", False,
                            ["нет flow с таким protocol+port"]))
        else:
            diffs = match_data_rule(cand[0], rule)
            results.append((f"data {rule.get('protocol')} {rule.get('port')}", not diffs, diffs))
    ok = bool(results) and all(ok_ for _, ok_, _ in results)
    return {"ok": ok, "results": results}


def check_fact(item: dict, client: LLMClient | None) -> dict:
    query = item["query"]
    must = FACTS_MUST_CONTAIN.get(item["id"], [])
    text, hits = answer_fact(client, query)
    # проверяем и сгенерированный ответ, и сырой фрагмент базы
    haystack = (text + " " + " ".join(h["text"] for h in hits)).lower()
    missing = [m for m in must if m.lower() not in haystack]
    has_citation = any(".md" in h["file"] for h in hits)
    return {"ok": not missing and has_citation,
            "detail": (f"нет подстроки: {missing}" if missing else
                       ("нет цитаты на файл базы" if not has_citation else ""))}


def check_out_of_scope(item: dict) -> dict:
    found = detect_unsupported(item["query"])
    return {"ok": bool(found), "detail": "" if found else "не распознано неподдерживаемое"}


def main() -> int:
    items = json.loads(BENCH_PATH.read_text(encoding="utf-8"))["items"]
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only:
        items = [i for i in items if i["id"] == only]

    client = LLMClient(Journal())
    _base, _model, _key = config.resolve_endpoint()
    print(f"Модель: {_model} (provider={config.active_provider()})")
    print(f"Сценариев: {len(items)}\n")

    passed = total = 0
    for item in items:
        qid, group = item["id"], item["group"]

        if group in ("full", "basic"):
            r = check_project(item, client, f"bench-{qid}")
            if "detail" in r and "results" not in r:
                print(f"{FAIL} {qid} ({group}): {r['detail']}")
                total += 1
                continue
            results = r["results"]
            total += len(results)
            ok_count = sum(1 for _, ok_, _ in results if ok_)
            passed += ok_count
            print(f"{PASS if r['ok'] else FAIL} {qid} ({group}): {ok_count}/{len(results)}")
            for label, ok_, diffs in results:
                if not ok_:
                    print(f"    {FAIL} {label}: {'; '.join(diffs)}")

        elif group == "facts":
            r = check_fact(item, client)
            total += 1
            passed += int(r["ok"])
            print(f"{PASS if r['ok'] else FAIL} {qid} ({group}): {r['detail'] or 'ответ + цитата ок'}")

        elif group == "out_of_scope":
            r = check_out_of_scope(item)
            total += 1
            passed += int(r["ok"])
            print(f"{PASS if r['ok'] else FAIL} {qid} ({group}): "
                  f"{'найдено: ' + ', '.join(detect_unsupported(item['query'])) if r['ok'] else r['detail']}")

        elif group == "incomplete":
            print(f"{SKIP} {qid} ({group}): уточняющие вопросы — зона участка A, пропущено")

    print(f"\nИтого: {passed}/{total} проверок пройдено")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
