import json
import os
from pathlib import Path
from uuid import uuid4
from urllib.request import Request, urlopen
from zipfile import ZipFile

with ZipFile(Path(os.environ["SYNONYX_CASE_ZIP"])) as archive:
    cases = json.loads(archive.read("synonyx_base/04_benchmarks.json").decode("utf-8-sig"))["items"]

def post(session, msg, current=None):
    req = Request(os.environ.get("SYNONYX_TEST_URL", "http://127.0.0.1:5173") + "/api/chat",
                  data=json.dumps({"session_id": session, "message": msg, "current_result": current}).encode(),
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=45) as response:
        return json.load(response)

def clarification(case, outcome):
    questions = outcome.get("questions") or []
    answers = []
    for q in questions:
        field = q["id"].rsplit(".", 1)[-1]
        if case == "N01":
            value = "Не знаю"
        elif case in ("F07", "F04", "N05"):
            checks = {"F04": "маска имени, размер, внешний антивирус", "F07": "внешний антивирус", "N05": "внешний антивирус"}
            values = {"port": "Не знаю", "source_checks": checks[case], "target_checks": "Без проверок",
                      "access_group": "Один подрядчик, разделение доступа не требуется" if case != "F04" else "Да",
                      "storage": "Файловый сервер цеха", "protocol": "SMB"}
            value = values.get(field)
            if field == "source_network_id":
                value = next((x for x in q["options"] if "офис" in x.casefold()), None)
            if value is None:
                return None
        else:
            return None
        answers.append(f"{q['text']} {value}" if len(questions) > 1 else value)
    return "\n".join(answers)

def rules_check(expected, result):
    keys = ("type", "from", "to", "mode", "protocol", "port", "checks")
    key = lambda r: json.dumps([r.get(k) for k in keys], ensure_ascii=False, sort_keys=True)
    actual_rules = result.get("rules", [])
    problems = []
    if result.get("rules_count") != expected["rules_count"]:
        problems.append("rule count")
    if sorted(map(key, actual_rules)) != sorted(map(key, expected["rules"])):
        problems.append("rule parameters")
    if result.get("file_users_count") != expected.get("file_users_count"):
        problems.append("file users")
    return problems

report = {}
output = Path("sessions") / "audit_results.json"
output.parent.mkdir(exist_ok=True)
for case in cases:
    label = case["id"]
    sid = f"audit-{label}-{uuid4().hex[:8]}"
    turns = []
    try:
        first = post(sid, case["query"])
        turns.append(first)
        o = first
        if label == "N05":
            o = post(sid, case["follow_up"]["user_answer"], o.get("result"))
            turns.append(o)
        for _ in range(3):
            answer = clarification(label, o)
            if not answer:
                break
            o = post(sid, answer, o.get("result"))
            turns.append(o)
        r = o.get("result") or {}
        text = o.get("text", "")
        if "не смогла извлечь" in text:
            problems = ["Groq extraction did not return usable JSON"]
        elif label == "N01":
            problems = [] if first.get("questions") and r.get("status") == "preliminary" and "минимум 1" in text else ["clarification or minimum"]
        elif label == "O01":
            problems = [] if r.get("requests_for_vendor") and "icap" in text.casefold() else ["unsupported feature response"]
        elif label in ("Q01", "Q10"):
            keywords = ("256",) if label == "Q01" else ("межсетев", "трафик", "синоникс")
            problems = [] if o.get("sources") and all(k in text.casefold() for k in keywords) else ["fact or sources"]
        elif label == "N05":
            problems = rules_check(case["follow_up"]["expected"], r)
            if (first.get("result") or {}).get("rules_count") != 1 or not first.get("questions"):
                problems.append("initial state")
        else:
            problems = rules_check(case["expected"], r)
        print(label, "OK" if not problems else "CHECK " + ", ".join(problems),
              f"turns={len(turns)} status={r.get('status')} rules={r.get('rules_count')}",
              "questions=" + ",".join(q["id"] for q in o.get("questions") or []), flush=True)
        report[label] = {"issues": problems, "turns": turns, "session_id": sid}
    except Exception as exc:
        print(label, "ERROR", type(exc).__name__, str(exc), flush=True)
        report[label] = {"issues": [str(exc)], "turns": turns, "session_id": sid}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

raise SystemExit(any(entry["issues"] for entry in report.values()))
