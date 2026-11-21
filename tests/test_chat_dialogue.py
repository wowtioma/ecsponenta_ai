"""Multi-turn checks against the real dialogue pipeline, with scripted LLM replies."""

import json
import unittest
import uuid
from copy import deepcopy
from unittest.mock import Mock, patch

import integration_test_server as server


NETWORKS = [
    {"id": "office", "name": "Офисная сеть", "trust": "open"},
    {"id": "shop", "name": "Сеть цеха", "trust": "closed"},
]
LOGS = {
    "id": "logs", "type": "data", "from": "shop", "to": "office",
    "description": "Журналы оборудования", "source_device": "Шлюз сбора",
    "recipient": "Сервер журналов", "protocol": "UDP", "port": 1514,
    "mode": "one-way", "reverse_forbidden": True,
}
CONTROL = {
    "id": "control", "type": "data", "from": "office", "to": "shop",
    "source_device": "Диспетчер", "recipient": "ПЛК линии",
    "description": "Опрос ПЛК", "protocol": "Modbus TCP", "port": 502,
    "mode": "two-way", "initiator_network_id": "office",
}
CLOCK = {
    "id": "clock", "type": "data", "from": "office", "to": "shop",
    "description": "Синхронизация времени", "source_device": "NTP-сервер офиса",
    "recipient": "Сервер времени цеха", "protocol": "UDP", "port": 123,
    "application_protocol": "NTP", "mode": "one-way",
}
FILES = {
    "id": "files", "type": "file", "from": "office", "to": "shop",
    "description": "Файлы отчётов", "source_device": "Оператор",
    "recipient": "Папка цеха", "mode": "one-way",
    "source_methods": [{"mode": "manual", "protocol": "SFTP"}],
    "target_methods": [{"mode": "PUSH", "protocol": "SMB"}],
    "access_group": "shared",
}


class ChatDialogueTests(unittest.TestCase):
    def setUp(self):
        self.llm = Mock()
        self.llm.chat.side_effect = AssertionError("Unexpected model call")
        client_patch = patch.object(server, "client", self.llm)
        client_patch.start()
        self.addCleanup(client_patch.stop)
        for attribute in ("sessions", "turns", "shown_questions", "last_project_messages", "pending_edits"):
            state = patch.object(server, attribute, {})
            state.start()
            self.addCleanup(state.stop)
        self.session_id = uuid.uuid4().hex
        self.result = None

    def script(self, *replies):
        self.llm.chat.side_effect = [
            (json.dumps(reply, ensure_ascii=False), None) if isinstance(reply, dict) else (reply, None)
            for reply in replies
        ]

    def send(self, message):
        reply = server.respond({
            "session_id": self.session_id,
            "message": message,
            "current_result": self.result,
        }, kb=None)
        if reply.get("result") is not None:
            self.result = deepcopy(reply["result"])
        return reply

    def start(self, *flows):
        self.script({"networks": NETWORKS, "flows": flows})
        return self.send("Свяжи открытую офисную и закрытую производственную сети.")

    def rules(self):
        return [(rule["protocol"], rule.get("port")) for rule in self.result["rules"]]

    def test_short_answers_bind_to_consecutive_questions(self):
        first = self.start({**LOGS, "recipient": None, "port": None})
        self.assertEqual([q["id"] for q in first["questions"]], ["logs.recipient"])
        second = self.send("Сервер журналов")
        self.assertEqual([q["id"] for q in second["questions"]], ["logs.port"])
        done = self.send("1514")
        self.assertEqual(done["questions"], [])
        self.assertEqual(done["result"]["status"], "completed")
        self.assertEqual(self.rules(), [("UDP", 1514)])
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_unknown_port_is_preserved_without_repeating_the_question(self):
        self.start({**LOGS, "port": None})
        reply = self.send("Не знаю")
        self.assertEqual(reply["questions"], [])
        self.assertEqual(self.result["status"], "preliminary")
        self.assertIn("logs.port", self.result["unknowns"])
        self.assertEqual(self.rules(), [("UDP", None)])
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_combined_form_can_answer_two_flows(self):
        initial = self.start({**LOGS, "port": None}, {**CONTROL, "port": None})
        values = {"logs.port": "1514", "control.port": "1502"}
        self.assertEqual({q["id"] for q in initial["questions"]}, values.keys())
        batch = "\n".join(f"{q['text']} {values[q['id']]}" for q in initial["questions"])
        done = self.send(batch)
        self.assertEqual(done["result"]["status"], "completed")
        self.assertEqual(self.rules(), [("UDP", 1514), ("Modbus TCP", 1502)])
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_file_checks_clear_after_answering_ui_form(self):
        initial = self.start(FILES)
        values = {"files.source_checks": "Размер", "files.target_checks": "Без проверок"}
        self.assertEqual({q["id"] for q in initial["questions"]}, values.keys())
        batch = "\n".join(f"{q['text']} {values[q['id']]}" for q in initial["questions"])
        checks = self.send(batch)
        self.assertEqual(
            [q["id"] for q in checks["questions"]],
            ["files.target_methods.0.storage"],
        )
        done = self.send("Папка отчётов на файловом сервере")
        self.assertEqual(done["result"]["status"], "completed")
        rule = done["result"]["rules"][0]
        self.assertEqual(rule["type"], "file")
        self.assertIn("размер", str(rule["checks_by_node"]).casefold())
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_reload_replays_existing_calculation_without_model(self):
        first = self.start(LOGS, CONTROL)
        self.result = None
        restored = self.send("Свяжи открытую офисную и закрытую производственную сети.")
        self.assertEqual(restored["text"], "Рассчитано правил: 2.")
        self.assertEqual(restored["result"]["rules"], first["result"]["rules"])
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_port_edit_is_local_and_repeat_is_idempotent(self):
        self.start(LOGS, CONTROL)
        edited = self.send("Поменяй порт у ПЛК на 1502")
        self.assertIn("502 → 1502", edited["text"])
        self.assertEqual(self.rules(), [("UDP", 1514), ("Modbus TCP", 1502)])
        repeated = self.send("Поменяй порт у ПЛК на 1502")
        self.assertTrue(repeated["result_unchanged"])
        self.assertIn("уже", repeated["text"])
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_rejected_mode_keeps_working_rules(self):
        self.start(LOGS, CONTROL)
        self.script({"flow_id": "control", "fields": {"direction": "one_way"}})
        reply = self.send("Сделай Modbus однонаправленным")
        self.assertTrue(reply["result_unchanged"])
        self.assertIn("двунаправленное", reply["text"])
        self.assertEqual(self.rules(), [("UDP", 1514), ("Modbus TCP", 502)])

    def test_explicit_receiver_name_beats_model_substitution(self):
        self.start(LOGS, CLOCK)
        self.script({
            "action": "add_recipient", "flow_id": "logs",
            "recipient": "Сервер времени цеха", "network_id": "shop",
        })
        self.send("Отправляй журналы ещё и на NTP-сервер офиса")
        self.assertEqual(self.rules(), [("UDP", 1514), ("UDP", 123), ("UDP", 1514)])
        receiver = self.result["rules"][-1]["to_device_id"]
        self.assertEqual(next(d["name"] for d in self.result["devices"] if d["id"] == receiver), "NTP-сервер офиса")

    def test_recipient_dialogue_continues_after_wrong_network(self):
        self.start(LOGS, CONTROL, CLOCK)
        self.script({
            "action": "add_recipient", "flow_id": "logs",
            "recipient": "Сервер времени цеха", "network_id": "shop",
        })
        self.assertTrue(self.send("Отправляй журналы ещё и на Сервер времени цеха")["result_unchanged"])
        wrong = self.send("ПЛК линии")
        self.assertTrue(wrong["result_unchanged"])
        self.assertIn("Офисная сеть", wrong["text"])
        call_count = self.llm.chat.call_count
        self.send("Архив журналов")
        self.assertEqual(self.rules()[-1], ("UDP", 1514))
        self.assertEqual(self.result["rules_count"], 4)
        self.assertEqual(self.llm.chat.call_count, call_count)

    def test_rename_known_recipient_keeps_protocols_and_other_flows(self):
        self.start(LOGS, CONTROL)
        self.script({"flow_id": "logs", "fields": {"recipient": "Архив смены"}})
        self.send("Переименуй сервер журналов в Архив смены")
        self.assertEqual(self.rules(), [("UDP", 1514), ("Modbus TCP", 502)])
        self.assertIn("Архив смены", [d["name"] for d in self.result["devices"]])
        self.assertNotIn("Сервер журналов", [d["name"] for d in self.result["devices"]])

    def test_parallel_sessions_do_not_share_pending_port(self):
        self.start({**LOGS, "port": None})
        first_id, first_result = self.session_id, self.result
        self.session_id, self.result = uuid.uuid4().hex, None
        self.start({**CONTROL, "port": None})
        self.send("1502")
        self.assertEqual(self.rules(), [("Modbus TCP", 1502)])
        self.session_id, self.result = first_id, first_result
        self.assertEqual(self.send("1514")["result"]["rules"][0]["protocol"], "UDP")
        self.assertEqual(self.rules(), [("UDP", 1514)])

    def test_question_does_not_become_recipient(self):
        self.start({**LOGS, "recipient": None})
        reply = self.send("Почему вы спрашиваете получателя?")
        self.assertNotEqual(server.sessions[self.session_id].flows[0].recipient, "Почему вы спрашиваете получателя?")
        self.assertTrue(any(q["id"] == "logs.recipient" for q in reply.get("questions", [])))
        self.assertIn("Получатель нужен", reply["text"])
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_ambiguous_port_edit_remembers_value_for_next_reply(self):
        self.start(LOGS, CONTROL)
        self.assertTrue(self.send("Поменяй порт на 1600")["result_unchanged"])
        reply = self.send("У сервера журналов")
        self.assertIn("1514 → 1600", reply["text"])
        self.assertEqual(self.rules(), [("UDP", 1600), ("Modbus TCP", 502)])
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_invalid_port_answer_keeps_question_and_explains_range(self):
        self.start({**LOGS, "port": None})
        reply = self.send("70000")
        self.assertIn("65535", reply["text"])
        self.assertEqual(reply["questions"][0]["id"], "logs.port")
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_question_about_existing_scheme_is_answered_without_reextracting(self):
        self.start(LOGS)
        reply = self.send("Почему здесь достаточно одного правила и кто принимает журналы?")
        self.assertIn("Сервер журналов", reply["text"])
        self.assertNotIn("Укажите, какой поток", reply["text"])
        self.assertEqual(self.rules(), [("UDP", 1514)])
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_model_cannot_remove_existing_flows_on_unknown_followup(self):
        self.start(LOGS, CONTROL)
        reply = self.send("Спасибо, понял")
        self.assertTrue(reply["result_unchanged"])
        self.assertEqual(self.rules(), [("UDP", 1514), ("Modbus TCP", 502)])
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_descriptive_clarification_only_fills_missing_fields(self):
        self.start({**LOGS, "recipient": None, "port": None}, CONTROL)
        self.script({"networks": NETWORKS, "flows": [{
            **LOGS, "recipient": "Сервис отчётов", "protocol": "TCP", "port": 1614,
        }]})
        reply = self.send("На стороне офиса журналы принимает выделенный сервис отчётов, который слушает порт 1614.")
        self.assertEqual(reply["result"]["status"], "completed")
        self.assertEqual(self.rules(), [("UDP", 1614), ("Modbus TCP", 502)])
        self.assertEqual(len(server.sessions[self.session_id].flows), 2)

    def test_explicit_new_flow_append_preserves_old_ports_and_recipients(self):
        self.start(LOGS, CONTROL)
        self.script({"networks": NETWORKS, "flows": [
            {**LOGS, "port": 9, "recipient": "Другой сервер"},
            CLOCK,
        ]})
        self.send("Добавь поток синхронизации времени из офиса в цех по NTP.")
        self.assertEqual(self.rules(), [("UDP", 1514), ("Modbus TCP", 502), ("UDP", 123)])
        self.assertEqual(server.sessions[self.session_id].flows[0].recipient, LOGS["recipient"])

    def test_explanation_between_edit_and_answer_preserves_pending_edit(self):
        self.start(LOGS, CONTROL)
        self.send("Поменяй порт на 1600")
        answer = self.send("Почему здесь два правила?")
        self.assertIn("2", answer["text"])
        self.assertTrue(answer["result_unchanged"])
        reply = self.send("У сервера журналов")
        self.assertIn("1514 → 1600", reply["text"])
        self.assertEqual(self.rules(), [("UDP", 1600), ("Modbus TCP", 502)])
        self.assertEqual(self.llm.chat.call_count, 1)


    def test_invalid_combined_form_does_not_partially_write_ports(self):
        first = self.start({**LOGS, "port": None}, {**CONTROL, "port": None})
        values = {"logs.port": "1514", "control.port": "70000"}
        batch = "\n".join(f"{q['text']} {values[q['id']]}" for q in first["questions"])
        reply = self.send(batch)
        self.assertEqual({q["id"] for q in reply["questions"]}, values.keys())
        self.assertEqual(
            [flow.port for flow in server.sessions[self.session_id].flows],
            [None, None],
        )
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_invalid_model_json_keeps_existing_configuration(self):
        self.start(LOGS, CONTROL)
        self.script("here is no valid JSON")
        reply = self.send("Переименуй шлюз сбора в Шлюз цеха")
        self.assertTrue(reply["result_unchanged"])
        self.assertEqual(self.rules(), [("UDP", 1514), ("Modbus TCP", 502)])
        self.assertEqual(server.sessions[self.session_id].flows[0].source_device, "Шлюз сбора")

    def test_duplicate_recipient_does_not_create_an_extra_rule(self):
        self.start(LOGS, CLOCK)
        self.script({"action": "add_recipient", "flow_id": "logs", "recipient": "Сервер журналов"})
        reply = self.send("Отправляй журналы также на сервер журналов")
        self.assertTrue(reply["result_unchanged"])
        self.assertEqual(self.rules(), [("UDP", 1514), ("UDP", 123)])

    def test_user_can_remove_a_specific_recipient_after_clarification(self):
        archive = {**LOGS, "id": "archive", "recipient": "Резервный архив"}
        self.start(LOGS, archive)
        ambiguous = self.send("Убери один из серверов журналов")
        self.assertTrue(ambiguous["result_unchanged"])
        self.assertEqual(self.result["rules_count"], 2)
        self.send("Резервный архив")
        self.assertEqual(self.result["rules_count"], 1)
        self.assertEqual(server.sessions[self.session_id].flows[0].recipient, "Сервер журналов")
        self.assertEqual(self.llm.chat.call_count, 1)
