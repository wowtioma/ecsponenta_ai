import json
import unittest
from unittest.mock import Mock

from b_adapter import session_from_extraction
from llm.extract import _normalize_flows, extract
from llm.vendor import detect_unsupported
from project_dialogue import merge_project_extraction
from rules import FileMethod, Flow, Network, Session, apply_answer, evaluate, record_unresolved_answer


NETWORKS = [Network(id="a", name="Диспетчерская", kind="open"),
            Network(id="b", name="Склад", kind="closed")]
SLOTS = [{"id": n.id, "name": n.name, "trust": n.kind} for n in NETWORKS]


def file_flow(flow_id, **changes):
    values = {
        "id": flow_id, "source_network_id": "a", "target_network_id": "b", "payload": "files",
        "direction": "one_way", "access_group": "shared", "source_checks": [], "target_checks": [],
        "source_methods": [FileMethod(mode="manual")], "target_methods": [FileMethod(mode="manual")],
    }
    return Flow(**(values | changes))


def data_flow(flow_id, **changes):
    values = {
        "id": flow_id, "source_network_id": "a", "target_network_id": "b", "payload": "data",
        "direction": "one_way", "protocol": "UDP", "port": 5514, "recipient": "Архив",
    }
    return Flow(**(values | changes))


def session(*flows, **changes):
    return Session(session_id="stress", **({"networks": NETWORKS, "flows": list(flows)} | changes))


def automatic(mode, *storages):
    return [FileMethod(mode=mode, protocol="SFTP", storage=name) for name in storages]


class EngineResilienceTests(unittest.TestCase):
    def test_explicit_reciprocal_automation_recovers_missing_llm_direction(self):
        only_forward = {
            "id": "flow-2", "type": "file", "from": "a", "to": "b", "mode": "one-way",
            "source_methods": [{"mode": "PULL", "protocol": "SMB", "storage": "Папка офиса"}],
            "target_methods": [{"mode": "PUSH", "protocol": "SMB", "storage": "Папка склада"}],
        }
        for flows in ([only_forward], [{**only_forward, "mode": "two-way"}]):
            with self.subTest(mode=flows[0]["mode"]):
                snapshot = {"networks": SLOTS, "flows": [dict(f) for f in flows]}
                _normalize_flows(snapshot,
                    "Хранилища Диспетчерской и Склада. Нужно выгружать файлы из обоих по расписанию "
                    "через SMB и автоматически доставлять в противоположное хранилище по SMB при поступлении. "
                    "Проверки одинаковые, общий доступ, ручных пользователей нет.")
                model = session_from_extraction("stress", snapshot)
                out = evaluate(model)
                self.assertEqual(out["result"]["rules_count"], 2)
                self.assertEqual(out["result"]["file_users_count"], 2)
                self.assertEqual({(r["from"], r["to"]) for r in out["result"]["rules"]}, {("a","b"),("b","a")})
                self.assertTrue(all(len(detail["methods"]) == 2 for detail in out["rule_details"].values()))

    def test_generic_reciprocal_request_keeps_reverse_details_unknown(self):
        snapshot = {"networks": SLOTS, "flows": [{
            "type": "file", "from": "a", "to": "b", "mode": "one-way",
            "source_methods": [{"mode": "USB"}], "target_methods": [{"mode": "manual"}],
            "access_group": "shared", "source_checks": [], "target_checks": [],
        }]}
        _normalize_flows(snapshot, "Файловый обмен между сетями нужен в обе стороны. Доставка в склад с USB.")
        self.assertEqual(len(snapshot["flows"]), 2)
        self.assertIsNone(snapshot["flows"][1]["source_methods"])
        self.assertIsNone(snapshot["flows"][1]["access_group"])
        result = evaluate(session_from_extraction("reverse", snapshot))["result"]
        self.assertEqual(result["status"], "preliminary")
        self.assertEqual(result["rules_count"], 1)

    def test_automatic_fan_in_reuses_confirmed_destination_per_rule(self):
        out = evaluate(session(file_flow("archives", source_methods=automatic("PULL", "A1", "A2", "A3"),
                                           target_methods=automatic("PUSH", "B")), manual_users_count=0))
        self.assertEqual((out["result"]["rules_count"], out["result"]["file_users_count"]), (3, 3))
        self.assertEqual([v["methods"]["b"][0]["storage"] for v in out["rule_details"].values()], ["B"] * 3)

    def test_fan_out_reuses_source_without_empty_rules(self):
        out = evaluate(session(file_flow("archives", source_methods=automatic("PULL", "A"),
                                           target_methods=automatic("PUSH", "B1", "B2")), manual_users_count=0))
        self.assertEqual((out["result"]["rules_count"], out["result"]["file_users_count"]), (2, 2))
        self.assertEqual([v["methods"]["a"][0]["storage"] for v in out["rule_details"].values()], ["A"] * 2)

    def test_ambiguous_many_to_many_requires_mapping(self):
        out = evaluate(session(file_flow("archives", source_methods=automatic("PULL", "A1", "A2"),
                                           target_methods=automatic("PUSH", "B1", "B2")), manual_users_count=0))
        self.assertEqual(out["result"]["rules_count"], 0)
        self.assertIn("archives.storage_mapping", out["result"]["unknowns"])

    def test_confirmed_storage_pairs_are_applied_without_cartesian_product(self):
        pending = session(file_flow("archives", source_methods=automatic("PULL", "A1", "A2"),
                                    target_methods=automatic("PUSH", "B1", "B2")), manual_users_count=0)
        configured = apply_answer(pending, "archives.storage_mapping", [("A1", "B2"), ("A2", "B1")])
        out = evaluate(configured)
        self.assertEqual(out["result"]["status"], "completed")
        self.assertEqual(out["result"]["rules_count"], 2)
        self.assertEqual({(d["methods"]["a"][0]["storage"], d["methods"]["b"][0]["storage"])
                          for d in out["rule_details"].values()}, {("A1", "B2"), ("A2", "B1")})

    def test_unsupported_feature_mentions_withdrawn_by_user_are_ignored(self):
        self.assertEqual(detect_unsupported(
            "Маршрутизация не нужна. Без встроенного антивируса. Отправляем архив."
        ), [])
        self.assertTrue(detect_unsupported("Нужен встроенный антивирус."))

    def test_usb_direction_conflict_is_reported_instead_of_flipped(self):
        snapshot = {"networks": SLOTS, "flows": [{
            "type":"file","from":"b","to":"a","mode":"one-way","access_group":"shared",
            "source_methods":[{"mode":"USB"}],"target_methods":[{"mode":"manual"}],
            "source_checks":[],"target_checks":[],
        }]}
        _normalize_flows(snapshot, "USB-отправитель находится в закрытой сети.")
        result = evaluate(session_from_extraction("usb-conflict", snapshot))["result"]
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["rules_count"], 0)

    def test_explicit_file_reverse_prohibition_prevents_pairing(self):
        forward = file_flow("reports", reverse_forbidden=True)
        backward = file_flow("backups", source_network_id="b", target_network_id="a", reverse_forbidden=True)
        out = evaluate(session(forward, backward, manual_users_count=2))
        self.assertEqual([rule["mode"] for rule in out["result"]["rules"]], ["one-way", "one-way"])

    def test_inverted_data_initiator_groups_by_actual_receiver(self):
        flows = [data_flow(str(i), target_network_id="b", initiator_network_id="b",
                           protocol="Modbus TCP", direction="two_way", port=502,
                           recipient="Диспетчер", source_device=f"ПЛК {i}") for i in range(3)]
        out = evaluate(session(*flows))
        self.assertEqual(out["result"]["rules_count"], 3)
        self.assertEqual({d["to_device_name"] for d in out["rule_details"].values()}, {"ПЛК 0", "ПЛК 1", "ПЛК 2"})

    def test_unknown_ports_do_not_merge_and_remain_preliminary(self):
        configs = session(data_flow("logs", port=None), data_flow("alarm", port=None))
        for flow in configs.flows:
            configs = record_unresolved_answer(configs, f"{flow.id}.port")
        result = evaluate(configs)["result"]
        self.assertEqual(result["status"], "preliminary")
        self.assertEqual(result["rules_count"], 2)
        self.assertTrue(all(rule["port"] is None for rule in result["rules"]))

    def test_empty_file_method_list_is_still_missing(self):
        out = evaluate(session(file_flow("empty", source_methods=[]), manual_users_count=1))
        self.assertEqual(out["result"]["rules_count"], 0)
        self.assertIn("empty.source_methods", out["result"]["unknowns"])

    def test_new_manual_flow_reopens_user_count_from_an_automatic_project(self):
        prior = session(file_flow("auto", source_methods=automatic("PULL", "Источник"),
                                  target_methods=automatic("PUSH", "Получатель")), manual_users_count=0)
        new = session(file_flow("manually", access_group="Инженеры"))
        combined = merge_project_extraction(prior, new, allow_addition=True)
        result = evaluate(combined)["result"]
        self.assertIn("manual_users_count", result["unknowns"])
        self.assertEqual(result["file_users_range"]["min"], 1)

    def test_automatic_only_rules_do_not_inherit_manual_user_count(self):
        prior = session(file_flow("auto", source_methods=automatic("PULL", "Источник"),
                                  target_methods=automatic("PUSH", "Получатель")), manual_users_count=8)
        result = evaluate(prior)["result"]
        self.assertEqual(result["file_users_count"], 1)

    def test_mixed_project_cannot_report_exact_licensing_with_incomplete_automation(self):
        ready = file_flow("manual")
        incomplete = file_flow("automated", source_methods=automatic("PULL", "Источник"), target_methods=None)
        result = evaluate(session(data_flow("log"), ready, incomplete, manual_users_count=3))["result"]
        self.assertEqual(result["rules_count"], 2)
        self.assertIsNone(result["file_users_count"])
        self.assertEqual(result["file_users_range"]["min"], 3)

    def test_mixed_257_distinct_rules_are_unsupported(self):
        flows = [data_flow(str(i), port=20000 + i) for i in range(256)]
        out = evaluate(session(*flows, file_flow("files"), manual_users_count=2))
        self.assertEqual(out["result"]["status"], "unsupported")
        self.assertEqual(out["result"]["rules_count"], 257)

    def test_bad_extraction_shape_gets_one_repair_and_no_duplicate_ids(self):
        client = Mock()
        client.chat.side_effect = [
            (json.dumps({"networks": [{"id":"a","name":"Диспетчерская"},{"id":"a","name":"Склад"}],
                         "flows":[]}), None),
            (json.dumps({"networks": SLOTS, "flows": [
                {"id":"flow-1","type":"data","from":"a","to":"b"},
                {"id":None,"type":"data","from":"b","to":"a"},
            ]}), None),
        ]
        result = extract(client, "Обмен телеметрией и журналами в обе стороны.")
        self.assertFalse(result.get("_fallback"))
        self.assertEqual(client.chat.call_count, 2)
        model = session_from_extraction("shape", result)
        self.assertEqual(len({flow.id for flow in model.flows}), 2)

    def test_explicit_mixed_intents_are_repaired_without_duplicate_ntp(self):
        file_part = {"type":"file","from":"a","to":"b","mode":"one-way"}
        incomplete = {"networks": SLOTS, "flows": [file_part]}
        recovered = {"networks": SLOTS, "flows": [
            file_part, {"type":"data","from":"b","to":"a","protocol":"UDP","port":5514},
            {"type":"data","from":"a","to":"b","protocol":"UDP","port":123,"application_protocol":"NTP"},
        ]}
        client = Mock()
        client.chat.side_effect = [(json.dumps(incomplete), None), (json.dumps(recovered), None)]
        result = extract(client, "Склад отправляет журналы по UDP 5514. TCP 514 не нужен. "
                                 "NTP-сервер диспетчерской передаёт время на склад по UDP 123. "
                                 "Также передаём файлы.")
        self.assertEqual(client.chat.call_count, 2)
        self.assertEqual(len(result["flows"]), 3)
        self.assertEqual([f.get("port") for f in result["flows"]], [None, 5514, 123])

    def test_prohibited_reverse_transfer_does_not_become_bidirectional(self):
        first = {"type":"file","from":"a","to":"b","mode":"one-way","access_group":"shared",
                 "source_methods":[{"mode":"manual"}],"target_methods":[{"mode":"manual"}],
                 "source_checks":[],"target_checks":[]}
        client = Mock()
        client.chat.side_effect = [
            (json.dumps({"networks": SLOTS, "flows": [first, {**first, "from":"b", "to":"a"}]}), None),
            (json.dumps({"networks": SLOTS, "flows": [first]}), None),
        ]
        normalized = extract(client, "Передаём файлы из Диспетчерской на Склад. У файла обратной передачи нет.")
        result = evaluate(session_from_extraction("ban", normalized))["result"]
        self.assertEqual(client.chat.call_count, 2)
        self.assertEqual(result["rules_count"], 1)
        self.assertEqual(result["rules"][0]["mode"], "one-way")

    def test_incomplete_repair_preserves_unresolved_intent(self):
        client = Mock()
        client.chat.return_value = (json.dumps({"networks": SLOTS, "flows": []}), None)
        result = extract(client, "Передаём журналы по UDP 5514 и передаём файлы.")
        self.assertEqual(client.chat.call_count, 2)
        model = session_from_extraction("missing-intent", result)
        self.assertEqual({flow.payload for flow in model.flows}, {"data", "files"})
        self.assertTrue(all(flow.source_network_id is None for flow in model.flows))
        self.assertEqual(evaluate(model)["result"]["status"], "needs_clarification")

    def test_history_does_not_become_evidence_for_new_file_checks(self):
        client = Mock()
        client.chat.return_value = (json.dumps({
            "networks": SLOTS, "flows": [{
                "type":"file","from":"a","to":"b","source_checks":None,"target_checks":None,
            }],
        }), None)
        output = extract(client, "В старом потоке антивирус и маска имени. Новое сообщение: добавь второй поток.",
                         evidence_text="Добавь второй поток.")
        self.assertIsNone(output["flows"][0]["source_checks"])
        self.assertIsNone(output["flows"][0]["target_checks"])

    def test_different_file_masks_remain_different_profiles(self):
        data = {"networks": SLOTS, "flows": [
            {"type":"file","from":"a","to":"b","mode":"one-way","access_group":"shared",
             "source_methods":[{"mode":"manual"}], "target_methods":[{"mode":"manual"}],
             "source_checks":[mask], "target_checks": []}
            for mask in ("маска имени: *.zip", "маска имени: *.log")
        ]}
        _normalize_flows(data,"Два ручных потока с разными масками имени.")
        result = evaluate(session_from_extraction("masks", data))["result"]
        self.assertEqual(result["rules_count"], 2)
        self.assertEqual({r["checks"][0] for r in result["rules"]}, {"маска имени: *.zip", "маска имени: *.log"})
