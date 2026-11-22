"""Compare exact rule objects against an organizer-provided ZIP archive."""

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from rules import Session, evaluate
from test_rules import data, files


def described(flow, description):
    return dict(flow, description=description)


def scenarios():
    journal = data("logs", "closed", "UDP", 514, "monitor")
    time = data("time", "open", "NTP", 123)
    usb = files("USB", ["ICAP: внешний антивирус"])
    usb["target_methods"][0]["trigger"] = "arrival"
    yield "F01", [
        described(dict(journal, id=f"lathe-{i}"), "Журналы событий трёх станков на сервер журналов")
        for i in range(3)
    ], {}
    yield "F02", [
        described(data("poll", "open", "Modbus TCP", 502, "controller", "open"),
                  "Опрос контроллера насосов программой диспетчера"),
        described(journal, "Журналы событий на сервер мониторинга"),
        described(time, "Синхронизация времени: от сервера времени общей сети на сервер времени станции"),
    ], {}
    yield "F04", [
        described(files("manual", ["маска имени", "размер", "ICAP: внешний антивирус"]),
                  "Файлы программ для станка"),
    ], {"manual_file_users": ["engineer"]}
    yield "F07", [
        described(data("mqtt", "closed", "MQTT", None, "office-broker", "closed"),
                  "Показания датчиков с брокера цеха на брокер офиса"),
        described(time, "Синхронизация времени: от сервера времени офиса на сервер времени цеха"),
        described(usb, "Обновления с флешки на файловый сервер цеха"),
    ], {"manual_file_users": ["contractor"], "unknown_answers": ["mqtt.port"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    with ZipFile(args.archive) as archive:
        benchmark = json.loads(archive.read("synonyx_base/04_benchmarks.json").decode("utf-8-sig"))
        example = json.loads(archive.read("result.example.json").decode("utf-8-sig"))
    cases = {case["id"]: case for case in benchmark["items"]}
    failures = []
    for case_id, flows, options in scenarios():
        expected = cases[case_id]["expected"]
        networks = [{"id": n["id"], "name": n["name"], "kind": n["trust"]} for n in expected["networks"]]
        session = Session(session_id=case_id, networks=networks, flows=flows, **options)
        actual = evaluate(session)["result"]
        mismatches = [key for key in expected if actual.get(key) != expected[key]]
        if case_id == "F02" and (actual.keys() != example.keys() or actual["schema_version"] != example["schema_version"]):
            mismatches.append("result.example.json fields or version")
        if mismatches:
            failures.append(case_id)
            print(f"{case_id}: FAIL ({', '.join(mismatches)})")
            for key in mismatches:
                if key in expected:
                    print(f"  {key}: expected {expected[key]!r}, got {actual.get(key)!r}")
        else:
            print(f"{case_id}: OK ({actual['rules_count']} rules)")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
