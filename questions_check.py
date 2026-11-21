"""Проверка генерации уточняющих вопросов на N01/N05 через РЕАЛЬНЫЙ код A.

Сценарий: extract() (B) -> b_adapter + rules.evaluate (A) выдаёт вопросы ->
rephrase_questions() (B) переформулирует их живым языком.

Запуск (из корня проекта, ключ в .env):
    python questions_check.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_ROOT = Path(__file__).resolve().parent
_CHECK_DIR = _ROOT / "_checkA"

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
from rules import evaluate  # noqa: E402

from llm import Journal, LLMClient, config, extract, rephrase_questions  # noqa: E402

BENCH = Path(config.ROOT) / "Кейс АйТи Бастион — Синоникс" / "synonyx_base" / "04_benchmarks.json"


def show(title: str, questions: list[dict]) -> None:
    print(f"  {title}: {len(questions)}")
    for q in questions:
        print(f"    [{q.get('id')}] {q.get('text')}")
        print(f"        варианты: {', '.join(q.get('options') or [])}")


def main() -> int:
    items = json.loads(BENCH.read_text(encoding="utf-8"))["items"]
    client = LLMClient(Journal())

    for qid in ("N01", "N05"):
        item = next(i for i in items if i["id"] == qid)
        print(f"\n=== {qid} ===")
        print("  запрос:", item["query"][:120])

        ext = extract(client, item["query"], session_id=f"q-{qid}", turn_id=1)
        session = session_from_extraction(f"q-{qid}", ext)
        out = evaluate(session)
        raw = out.get("questions") or []
        show("A выдал вопросов (заготовленные)", raw)

        if not raw:
            print("  уточнений не требуется")
            continue

        framed = rephrase_questions(
            client, raw, item["query"], session_id=f"q-{qid}", turn_id=2
        )
        show("B переформулировал", framed)

        # id и варианты обязаны сохраниться — иначе A не применит ответы.
        ok_ids = [q["id"] for q in raw] == [q["id"] for q in framed]
        ok_opts = all(set(q["options"]) <= set(f["options"]) for q, f in zip(raw, framed))
        print(f"  id сохранены: {ok_ids} | варианты не потеряны: {ok_opts}")
        if not (ok_ids and ok_opts):
            print("  ОШИБКА: контракт с A нарушен")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
