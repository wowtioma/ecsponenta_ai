"""Проверка стыка B -> A на РЕАЛЬНОМ коде участка A (не мок).

Берёт extract() участка B, прогоняет через b_adapter.session_from_extraction и
rules.evaluate и сравнивает с эталонами 04_benchmarks.json.

Исходники A подтягиваются из ветки origin/A автоматически (в _checkA/).

Запуск (из корня проекта, ключ в .env):
    python contract_check.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_CHECK_DIR = _ROOT / "_checkA"

# --- подтянуть исходники A из git, если их нет ---
_CHECK_DIR.mkdir(exist_ok=True)
for _name in ("rules.py", "b_adapter.py"):
    _target = _CHECK_DIR / _name
    if not _target.exists():
        _out = subprocess.run(
            ["git", "show", f"origin/A:{_name}"], cwd=_ROOT, capture_output=True
        )
        if _out.returncode != 0:
            print(f"Не удалось получить {_name} из origin/A. Сделай: git fetch origin A")
            raise SystemExit(1)
        _target.write_bytes(_out.stdout)

sys.path.insert(0, str(_CHECK_DIR))

from b_adapter import session_from_extraction  # noqa: E402
from rules import evaluate, record_unresolved_answer  # noqa: E402

from llm import Journal, LLMClient, config, extract  # noqa: E402

BENCH = Path(config.ROOT) / "Кейс АйТи Бастион — Синоникс" / "synonyx_base" / "04_benchmarks.json"
KEYS = ("type", "from", "to", "mode", "protocol", "port", "checks")


def rule_key(rule: dict) -> str:
    return json.dumps([rule.get(k) for k in KEYS], ensure_ascii=False, sort_keys=True)


def main() -> int:
    items = json.loads(BENCH.read_text(encoding="utf-8"))["items"]
    client = LLMClient(Journal())
    total_ok = 0
    total = 0

    for qid in ("F01", "F02", "F04", "F07"):
        item = next(i for i in items if i["id"] == qid)
        expected = item["expected"]

        ext = extract(client, item["query"], session_id=f"a-{qid}", turn_id=1)
        session = session_from_extraction(f"a-{qid}", ext)
        out = evaluate(session)

        # Как в аудите: на уточнения отвечаем «Не знаю» и пересчитываем.
        for _ in range(2):
            pending = out.get("questions") or []
            if not pending:
                break
            for q in pending:
                session = record_unresolved_answer(session, q["id"])
            out = evaluate(session)

        result = out["result"]
        questions = out.get("questions") or []

        problems = []
        if result.get("rules_count") != expected["rules_count"]:
            problems.append(
                f"rules_count {result.get('rules_count')} != {expected['rules_count']}"
            )
        if sorted(map(rule_key, result.get("rules", []))) != sorted(map(rule_key, expected["rules"])):
            problems.append("rule params")
        if result.get("file_users_count") != expected.get("file_users_count"):
            problems.append(
                f"file_users {result.get('file_users_count')} != {expected.get('file_users_count')}"
            )
        if questions:
            problems.append("остались вопросы: " + ",".join(q["id"] for q in questions))

        total += 1
        total_ok += not problems
        mark = "OK  " if not problems else "FAIL"
        print(
            f"{mark} {qid}: rules={result.get('rules_count')} "
            f"status={result.get('status')} users={result.get('file_users_count')} "
            f"questions={len(questions)}"
        )
        for p in problems:
            print("      -", p)
        for rule in result.get("rules", []):
            print("      ", json.dumps({k: rule.get(k) for k in KEYS}, ensure_ascii=False))

    print(f"\nСтык B -> A: {total_ok}/{total} сценариев совпали с эталоном")
    return 0 if total_ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
