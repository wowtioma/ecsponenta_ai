"""Multi-turn checks against the real dialogue pipeline, with scripted LLM replies."""

import json
import unittest
import uuid
from copy import deepcopy
from unittest.mock import Mock, patch

import integration_test_server as server
from llm.client import GroqRateLimit


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
        wording_patch = patch.object(server, "MODEL_WORDING_ENABLED", False)
        wording_patch.start()
        self.addCleanup(wording_patch.stop)
        for attribute in ("sessions", "turns", "shown_questions", "last_project_messages", "pending_edits", "pending_antivirus"):
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

    def send(self, message, answers=None):
        reply = server.respond({
            "session_id": self.session_id,
            "message": message,
            "current_result": self.result,
            "answers": answers,
        }, kb=None)
        if reply.get("result") is not None:
            self.result = deepcopy(reply["result"])
        return reply

    def start(self, *flows):
        self.script({"networks": NETWORKS, "flows": flows})
        return self.send("Свяжи открытую офисную и закрытую производственную сети.")

    def rules(self):
        return [(rule["protocol"], rule.get("port")) for rule in self.result["rules"]]

    def test_three_network_request_stops_before_flow_questions(self):
        snapshot = {"networks": [*NETWORKS, {"id": "vendor", "name": "Подрядчики", "trust": "unknown"}], "flows": []}
        self.script(snapshot, snapshot)
        reply = self.send("Нужно одним Синониксом связать офис, цех и отдельную сеть подрядчиков")
        self.assertEqual(self.result["status"], "unsupported")
        self.assertEqual(reply["questions"], [])
        self.assertIn("Выберите одну пару", reply["text"])
        self.assertEqual(self.llm.chat.call_count, 2)
        self.start(LOGS)
        self.assertEqual(self.result["status"], "completed")

    def test_three_extracted_networks_stop_before_calculation(self):
        snapshot = {"networks": [*NETWORKS, {"id": "guest", "name": "Гости", "trust": "unknown"}], "flows": []}
        self.script(snapshot, snapshot)
        reply = self.send("Нужен обмен между площадками")
        self.assertEqual(self.result["status"], "unsupported")
        self.assertEqual(reply["questions"], [])

    def test_unknown_flows_explains_missing_information_and_can_resume(self):
        self.start()
        reply = self.send("Не знаю")
        self.assertIn("flows", self.result["unknowns"])
        self.assertIn("недостаточно сведений", reply["text"])
        self.assertEqual(reply["questions"], [])
        self.script({"networks": NETWORKS, "flows": [{**LOGS, "port": 514}]})
        self.send("Цех отправляет журналы на сервер в офисе по UDP 514.")
        self.assertEqual(self.rules(), [("UDP", 514)])

    def test_f04_local_push_is_part_of_the_same_cross_network_file_flow(self):
        incoming = {**FILES, "id": "incoming", "description": "ручная передача файлов",
                    "target_methods": None, "source_checks": ["маска имени", "размер", "ICAP: внешний антивирус"],
                    "target_checks": None, "access_group": "shared"}
        local = {**FILES, "id": "local-push", "from": "shop",
                 "source_methods": None, "target_methods": [{"mode": "PUSH", "protocol": "SMB", "storage": "Архив"}]}
        for target in ("shop", None):
            with self.subTest(target=target):
                self.session_id = uuid.uuid4().hex
                self.result = None
                self.script({"networks": NETWORKS, "flows": [incoming, {**local, "to": target}],
                             "manual_file_users": ["Инженер"]})
                reply = self.send("Один инженер офиса вручную передаёт файлы по SFTP в закрытый сегмент; "
                                  "там устройство автоматически доставляет их в хранилище по SMB/PUSH. "
                                  "Требуются маска имени, проверка размера и внешний антивирус по ICAP. "
                                  "Разных групп доступа и разных профилей проверок нет")
                self.assertEqual(reply["result"]["rules_count"], 1)
                self.assertEqual(reply["result"]["file_users_count"], 1)
                self.assertEqual(reply["result"]["rules"][0]["methods_by_node"]["shop"][0]["protocol"], "SMB")
                self.assertNotIn("границу", reply["text"])

    def test_bidirectional_questions_name_each_direction_and_stage_methods(self):
        flow = {"type": "file", "description": "Обмен файлами", "mode": "one-way"}
        self.script({"networks": NETWORKS, "flows": [
            {**flow, "from": "office", "to": "shop"}, {**flow, "from": "shop", "to": "office"},
        ]})
        initial = self.send("Между офисом и закрытой сетью цеха нужно обмениваться файлами в обе стороны")
        questions = initial["questions"]
        self.assertEqual(len(questions), 4)
        self.assertEqual(len({q["text"] for q in questions}), 4)
        self.assertTrue(any("Офисная сеть → Сеть цеха" in q["text"] for q in questions))
        self.assertTrue(any("Сеть цеха → Офисная сеть" in q["text"] for q in questions))
        following = self.send("Не знаю", {q["id"]: "Не знаю" for q in questions})
        self.assertTrue(any(q["id"].endswith(".access_group") for q in following["questions"]))
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_bidirectional_transfer_needs_two_rules_once_both_automations_use_same_node(self):
        flow = {"type": "file", "mode": "one-way", "description": "Документы"}
        self.script({"networks": NETWORKS, "flows": [
            {**flow, "id": "outbound", "from": "office", "to": "shop"},
            {**flow, "id": "inbound", "from": "shop", "to": "office"},
        ]})
        initial = self.send("Между офисом и закрытой сетью цеха нужно обмениваться файлами в обе стороны")
        self.assertIn("минимум 1", initial["text"])
        methods = self.send("Способы передачи", {
            "outbound.source_methods": "USB", "outbound.target_methods": "Автоматически в хранилище",
            "inbound.source_methods": "PULL", "inbound.target_methods": "Заберёт человек вручную",
        })
        self.assertEqual(methods["result"]["rules_count"], 0)
        self.assertIn("минимум 2", methods["text"])
        details = self.send("Одинаковые настройки, один сотрудник", {
            **{question["id"]: "Да" if question["id"].endswith(".access_group") else "Без проверок"
               for question in methods["questions"] if question["id"] != "manual_users_count"},
            "manual_users_count": "1",
        })
        self.assertEqual({question["id"] for question in details["questions"]}, {
            "inbound.source_methods.0.protocol", "inbound.source_methods.0.storage",
            "outbound.target_methods.0.protocol", "outbound.target_methods.0.storage",
        })
        done = self.send("Хранилища согласованы", {
            "inbound.source_methods.0.protocol": "SFTP", "inbound.source_methods.0.storage": "Отчёты цеха",
            "outbound.target_methods.0.protocol": "SMB", "outbound.target_methods.0.storage": "Обновления цеха",
        })
        result = done["result"]
        self.assertEqual((result["status"], result["rules_count"], result["file_users_count"]), ("completed", 2, 2))
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_destination_and_custom_methods_for_incomplete_update_delivery(self):
        update = {**FILES, "id":"patches", "from":"shop", "to":"office",
                  "source_methods":None, "target_methods":None, "recipient":None,
                  "source_device":None, "access_group": None}
        self.script({"networks": NETWORKS, "flows": [{**LOGS, "port": 514}, update]})
        first = self.send("Из закрытого цеха отправляем журналы одному офисному серверу по UDP 514, "
                          "обратного обмена не нужно. Ещё нужно передавать обновления в цех")
        by_id = {q["id"]: q for q in first["questions"]}
        self.assertIn("USB", by_id["patches.source_methods"]["options"])
        self.assertNotIn("На флешку", by_id["patches.target_methods"]["options"])
        second = self.send("Уточнение передачи", {
            "patches.source_methods":"вручную по USB", "patches.target_methods":"по smb push",
            "patches.source_checks":"Без проверок", "patches.target_checks":"Проверка по ICAP",
            "patches.access_group":"Да", "manual_users_count":"1",
        })
        self.assertEqual([q["id"] for q in second["questions"]], ["patches.target_methods.0.storage"])
        done = self.send("Сервер цеха")
        self.assertEqual(done["result"]["status"], "completed")
        self.assertEqual(self.rules()[0], ("UDP", 514))
        self.assertEqual(done["result"]["rules_count"], 2)
        self.assertEqual(done["result"]["file_users_count"], 1)

    def test_firewall_question_with_adverb_goes_to_knowledge_base(self):
        hits = [{"file":"02_methodology.md","section":"2. Размещение"}]
        with patch.object(server, "answer_fact", return_value=("Разные функции устройств.", hits)) as fact:
            result = self.send("Зачем ещё нужен межсетевой экран, если уже стоит Синоникс?»")
        fact.assert_called_once()
        self.llm.chat.assert_not_called()
        self.assertEqual(result["sources"], hits)
        self.assertNotIn("result", result)

    def test_update_package_clarification_preserves_udp_rule(self):
        self.script({"networks": NETWORKS, "flows": [LOGS, {
            "id": "patches", "type": "data", "from": "office", "to": "shop",
            "description": "Обновления ПО", "protocol": None, "mode": "one-way",
        }]})
        first = self.send("Отправляем журналы в офис. Также нужно доставлять обновления ПО в цех.")
        question = next(q for q in first["questions"] if q["id"] == "patches.source_methods")
        self.assertEqual(len(self.rules()), 1)
        deferred = self.send(question["text"] + " Не знаю")
        self.assertTrue(any(q["id"] == "patches.target_methods" for q in deferred["questions"]))
        self.assertIn("patches.source_methods", self.result["unknowns"])
        self.script({"networks": NETWORKS, "manual_file_users": ["Сотрудник"], "flows": [{
            **FILES, "id": "new-id", "source_methods": [{"mode": "USB"}],
            "target_methods": [{"mode": "PUSH", "protocol": "SMB", "storage": "Хранилище", "trigger": "arrival"}],
            "source_checks": ["ICAP: внешний антивирус"], "target_checks": [],
        }]})
        reply = self.send("Один сотрудник приносит обновления на USB. Они должны попадать на сервер по SMB после проверки по ICAP.")
        self.assertEqual((self.result["rules_count"], self.result["file_users_count"]), (2, 1))
        self.assertEqual(reply["questions"], [])
        self.assertEqual(self.rules()[0], ("UDP", 1514))
        usb_rule = self.result["rules"][1]
        devices = {device["id"]: device["name"] for device in self.result["devices"]}
        self.assertNotIn("from_device_id", usb_rule)
        self.assertEqual(devices[usb_rule["to_device_id"]], "Хранилище")

    def test_n05_accepts_user_count_in_words_and_names_deferred_delivery(self):
        patches = {**FILES, "source_methods": None, "target_methods": None,
                   "description": "Обновления в цех", "access_group": None}
        for count in ("один", "один файловый пользователь", "1"):
            with self.subTest(count=count):
                self.session_id = uuid.uuid4().hex
                self.result = None
                initial = self.start({**LOGS, "port": 514}, patches)
                answers = {"files.source_methods": "USB", "files.target_methods": "Не знаю",
                           "files.access_group": "Да", "files.source_checks": "Без проверок",
                           "files.target_checks": "Внешний антивирус по ICAP"}
                self.send("\n".join(f"{q['text']} {answers[q['id']]}"
                                    for q in initial["questions"] if q["id"] in answers))
                partial = self.send(count)
                self.assertEqual(server.sessions[self.session_id].manual_users_count, 1)
                self.assertEqual(self.result["unknowns"], ["files.target_methods"])
                self.assertEqual(self.result["rules_count"], 1)
                self.assertIn("Обновления в цех", partial["text"])
                self.assertIn("способ доставки", partial["text"])
                delivery = self.send("Автоматически в хранилище")
                values = {"protocol": "SMB", "storage": "Файловый сервер цеха"}
                self.send("\n".join(f"{q['text']} {values[q['id'].rsplit('.', 1)[-1]]}"
                                    for q in delivery["questions"]))
                self.assertEqual(self.result["status"], "completed")
                self.assertEqual(self.result["rules_count"], 2)
                self.assertEqual(self.result["file_users_count"], 1)

    def test_storage_pipelines_with_common_unknown_checks(self):
        def pipeline(source, target):
            return {"type": "file", "mode": "two-way", "from": source, "to": target,
                    "source_methods": [{"mode": "PULL", "protocol": "SFTP", "storage": source}],
                    "target_methods": [{"mode": "PUSH", "protocol": "SFTP", "storage": target}],
                    "access_group": "shared"}
        self.script({"networks": NETWORKS, "flows": [pipeline("office", "shop"), pipeline("shop", "office")]})
        self.send("Два хранилища обмениваются файлами. Проверки одинаковые, ручных пользователей нет.")
        self.assertEqual((self.result["rules_count"], self.result["file_users_count"]), (2, 2))
        self.assertEqual(self.result["status"], "preliminary")

    def test_symmetric_storage_flow_joins_separate_pull_and_push_records(self):
        flow = {
            "type": "file", "mode": "one-way", "from": "office", "to": "shop",
            "source_methods": None, "target_methods": None,
        }
        self.script({"networks": NETWORKS, "flows": [
            {**flow, "description": "Забор файлов из офисного хранилища",
             "source_methods": [{"mode": "PULL", "protocol": "SFTP", "storage": "Офисное хранилище"}],
             "recipient": "Синоникс"},
            {**flow, "description": "Доставка файлов в хранилище закрытого цеха",
             "target_methods": [{"mode": "PUSH", "protocol": "SFTP", "storage": "Хранилище закрытого цеха"}],
             "source_device": "Синоникс"},
        ]})
        reply = self.send(
            "Есть офисное хранилище и хранилище закрытого цеха. Синоникс должен забирать файлы из каждого "
            "по расписанию через SFTP и доставлять их во второе через SFTP сразу после поступления. "
            "Ручных пользователей нет, проверки одинаковые, разделять доступ не нужно"
        )
        result = reply["result"]
        self.assertEqual((result["status"], result["rules_count"], result["file_users_count"]), ("preliminary", 2, 2))
        self.assertEqual({q["id"] for q in reply["questions"]}, {"file_checks:office", "file_checks:shop"})
        stores = {"office": "Офисное хранилище", "shop": "Хранилище закрытого цеха"}
        for rule in result["rules"]:
            self.assertEqual(rule["mode"], "one-way")
            self.assertEqual(rule["methods_by_node"][rule["from"]], [
                {"mode": "PULL", "protocol": "SFTP", "storage": stores[rule["from"]], "trigger": "schedule"},
            ])
            self.assertEqual(rule["methods_by_node"][rule["to"]], [
                {"mode": "PUSH", "protocol": "SFTP", "storage": stores[rule["to"]], "trigger": "arrival"},
            ])
        done = self.send("Подтверждаю проверки", {"file_checks:office": "Без проверок", "file_checks:shop": "Без проверок"})
        self.assertEqual((done["result"]["status"], done["result"]["rules_count"]), ("completed", 2))
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_access_groups_are_not_counted_as_separate_networks(self):
        mistaken_networks = [*NETWORKS, {"id": "dept", "name": "Отдел закупок", "trust": "open"}]
        flows = [{
            **FILES, "id": group, "access_group": group,
            "target_methods": [{"mode": "manual", "protocol": "SFTP"}],
        } for group in ["Продажи", "Закупки"]]
        self.script(
            {"networks": mistaken_networks, "flows": []},
            {"networks": NETWORKS, "flows": flows},
        )
        initial = self.send("Два отдела одной офисной сети вручную отправляют файлы в закрытый цех. Проверки одинаковые, полученные файлы отделов изолированы.")
        self.assertEqual(initial["result"]["rules_count"], 2)
        self.assertIsNone(initial["result"]["file_users_count"])
        self.assertIn("manual_users_count", initial["result"]["unknowns"])
        self.assertEqual(initial["result"]["status"], "preliminary")

    def test_builtin_antivirus_request_can_continue_with_icap(self):
        request = self.send("Хочу передавать файлы и проверять встроенным антивирусом.")
        self.assertEqual(request["result"]["status"], "unsupported")
        self.assertIn("ICAP", request["text"])
        self.script({
            "networks": NETWORKS,
            "manual_file_users": ["Отправитель"],
            "flows": [{
                **FILES, "target_methods": [{"mode": "manual", "protocol": "SFTP"}],
                "source_checks": [], "target_checks": ["ICAP: внешний антивирус"],
            }],
        })
        done = self.send("Да, есть внешний антивирус по ICAP.")
        self.assertEqual(done["result"]["rules_count"], 1)
        self.assertIn("ICAP: внешний антивирус", done["result"]["rules"][0]["checks"])
        self.assertTrue(any("встроенный антивирус" in item for item in done["result"]["requests_for_vendor"]))

    def test_recipient_roles_and_explicit_unknown_port_survive_extraction(self):
        self.script({"networks": NETWORKS, "flows": [
            {**LOGS, "recipient": None, "port": 514},
            {**LOGS, "id": "mqtt", "protocol": "MQTT", "recipient": None,
             "port": 1883, "mode": "two-way", "reverse_forbidden": None},
        ]})
        reply = self.send("Из цеха передаём журналы одному офисному серверу по UDP 514. "
                          "Брокер передаёт показания брокеру офиса. Порт MQTT неизвестен.")
        self.assertEqual(self.rules(), [("UDP", 514), ("MQTT", None)])
        self.assertEqual(reply["result"]["status"], "preliminary")
        self.assertIn("mqtt.port", reply["result"]["unknowns"])

    def test_explicit_automatic_delivery_is_kept_when_model_omits_it(self):
        self.script({
            "networks": NETWORKS, "manual_file_users": ["Инженер"],
            "flows": [{**FILES, "target_methods": None, "source_checks": [], "target_checks": []}],
        })
        reply = self.send("Инженер вручную отправляет файлы по SFTP. В цехе файлы должны "
                          "автоматически попадать в общую папку файлового сервера по SMB.")
        rule = reply["result"]["rules"][0]
        self.assertEqual(rule["methods_by_node"]["shop"], [
            {"mode": "PUSH", "protocol": "SMB", "storage": "общую папку файлового сервера"},
        ])

    def test_explicit_reciprocal_automation_corrects_reversed_method(self):
        self.script({"networks": NETWORKS, "flows": [
            {**FILES, "id": "forward", "source_methods": None, "target_methods": [{"mode": "PULL", "storage": "Цех"}]},
            {**FILES, "id": "reverse", "from": "shop", "to": "office",
             "source_methods": [{"mode": "PULL", "storage": "Цех"}], "target_methods": None},
        ]})
        reply = self.send("Файлы забирать из каждого хранилища по расписанию через SFTP "
                          "и доставлять во второе сразу после поступления. Ручных пользователей нет, проверки одинаковые.")
        self.assertEqual((reply["result"]["rules_count"], reply["result"]["file_users_count"]), (2, 2))
        self.assertEqual(reply["result"]["status"], "preliminary")

    def test_explicit_reverse_workflow_resolves_two_way_clarification(self):
        forward = {**FILES, "id": "files", "mode": "two-way", "source_checks": [], "target_checks": [],
                   "target_methods": [{"mode": "PUSH", "protocol": "SMB", "storage": "Цех"}]}
        reply = self.start(LOGS, forward)
        self.assertIn("files.file_directions", [q["id"] for q in reply["questions"]])
        self.script({"networks": NETWORKS, "manual_file_users": ["Оператор"], "flows": [
            {**forward, "mode": "one-way"},
            {**forward, "id": "reverse", "from": "shop", "to": "office", "mode": "one-way",
             "source_methods": [{"mode": "PULL", "protocol": "SFTP", "storage": "Цех"}],
             "target_methods": [{"mode": "PUSH", "protocol": "SFTP", "storage": "Офис"}]},
        ]})
        done = self.send("Из цеха в офис: автоматический забор SFTP из цеха и доставка в офис по SFTP.")
        self.assertEqual(done["result"]["status"], "completed")
        self.assertEqual(done["result"]["rules_count"], 3)
        self.assertEqual(done["result"]["file_users_count"], 2)
        self.assertEqual(self.rules()[0], ("UDP", 1514))

    def test_known_target_is_not_offered_as_the_other_network(self):
        self.script({"networks": [NETWORKS[1]], "flows": [{
            **FILES, "from": None, "target_methods": None,
        }]})
        reply = self.send("Нужно передавать обновления в закрытую сеть цеха.")
        self.assertEqual([q["id"] for q in reply["questions"]], ["networks"])
        self.assertEqual(reply["questions"][0]["options"], ["Открытая сеть"])
        self.send("Открытая сеть", {"networks": "Открытая сеть"})
        current = server.sessions[self.session_id]
        self.assertEqual(current.flows[0].source_network_id, "open")
        self.assertEqual(current.flows[0].target_network_id, "shop")
        self.assertEqual(sum(call.kwargs["purpose"] == "extract" for call in self.llm.chat.call_args_list), 1)

    def test_usb_option_is_available_only_on_the_open_network(self):
        values = {**FILES, "source_methods": None, "target_methods": None, "access_group": None}
        reply = self.start(values, {**values, "id": "reverse", "from": "shop", "to": "office"})
        questions = {q["id"]: q["options"] for q in reply["questions"]}
        self.assertIn("USB", questions["files.source_methods"])
        self.assertNotIn("USB", questions["reverse.source_methods"])
        self.assertNotIn("На флешку", questions["files.target_methods"])
        self.assertIn("На флешку", questions["reverse.target_methods"])

    def test_two_deferred_file_settings_apply_in_one_message(self):
        reply = self.start({
            **FILES, "source_methods": [{"mode": "USB"}], "source_checks": [], "target_checks": [],
        })
        self.assertEqual({q["id"] for q in reply["questions"]}, {
            "files.target_methods.0.storage", "manual_users_count",
        })
        self.send("Пока не знаю", {q["id"]: "Не знаю" for q in reply["questions"]})
        done = self.send("Хранилище — файловый сервер цеха. Обновления на флешке приносит один сотрудник.")
        self.assertEqual(done["result"]["status"], "completed")
        self.assertEqual(done["result"]["file_users_count"], 1)
        self.assertEqual(done["result"]["rules"][0]["methods_by_node"]["shop"][0]["storage"], "файловый сервер цеха")
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_same_checks_are_agreed_once_per_network(self):
        def flow(source, target):
            return {
                **FILES, "id": source, "from": source, "to": target,
                "source_methods": [{"mode": "PULL", "protocol": "SFTP", "storage": source}],
                "target_methods": [{"mode": "PUSH", "protocol": "SFTP", "storage": target}],
            }
        self.script({"networks": NETWORKS, "flows": [flow("office", "shop"), flow("shop", "office")]})
        reply = self.send("Ручных пользователей нет, проверки одинаковые.")
        self.assertEqual(reply["result"]["rules_count"], 2)
        self.assertEqual(reply["result"]["file_users_count"], 2)
        self.assertEqual(len(reply["questions"]), 2)
        done = self.send("Проверки согласованы", {
            "file_checks:office": "Без проверок", "file_checks:shop": "Маска имени",
        })
        self.assertEqual(done["result"]["status"], "completed")
        self.assertEqual(done["result"]["rules_count"], 2)
        self.assertTrue(all(rule["checks_by_node"]["shop"] == ("маска имени",)
                            for rule in done["result"]["rules"]))
        first, second = done["result"]["rules"]
        self.assertEqual(first["from_device_id"], second["to_device_id"])
        self.assertEqual(first["to_device_id"], second["from_device_id"])
        self.assertEqual(len(done["result"]["devices"]), 2)

    def test_opposite_storage_flows_keep_explicit_checks_and_ask_for_missing_protocol(self):
        networks = [
            {**NETWORKS[0], "name": "Офисная сеть логистики"},
            {**NETWORKS[1], "name": "Сеть холодильной автоматики"},
        ]
        plans = {
            **FILES, "id": "plans", "description": "Планы смен", "access_group": None,
            "source_device": "Планы смен", "recipient": "Планы к исполнению",
            "source_checks": ["маска имени"], "target_checks": None,
            "source_methods": [{"mode": "PULL", "protocol": "SMB", "storage": "Планы смен"}],
            "target_methods": [{"mode": "PUSH", "protocol": None, "storage": "Планы к исполнению"}],
        }
        reports = {
            **plans, "id": "reports", "from": "shop", "to": "office", "description": "Отчёты камер",
            "source_device": "Отчёты камер", "recipient": "Архив отчётов", "source_checks": ["размер"],
            "source_methods": [{"mode": "PULL", "protocol": "FTP", "storage": "Отчёты камер"}],
            "target_methods": [{"mode": "PUSH", "protocol": "SMB", "storage": "Архив отчётов"}],
        }
        self.script({"networks": networks, "flows": [LOGS, CONTROL, plans, reports]})
        reply = self.send(
            "Из закрытой сети холодильной автоматики идут журналы по UDP 1514, из офисной сети "
            "логистики опрашиваем контроллер по Modbus TCP 502. Файлы ходят в обе стороны. "
            "Из папки «Планы смен» забираем по SMB и доставляем в «Планы к исполнению». "
            "Протокол доставки пока неизвестен. На офисной стороне проверяем маску имени, "
            "на стороне автоматики дополнительных проверок нет. В обратную сторону забираем "
            "из «Отчёты камер» по FTP и доставляем в «Архив отчётов» по SMB. На закрытой стороне "
            "проверяем размер, на офисной стороне дополнительных проверок нет. "
            "Ручных пользователей нет. Разделять доступ к файлам не нужно."
        )
        self.assertEqual(reply["result"]["rules_count"], 3)
        self.assertEqual(reply["result"]["rules"][-1]["checks_by_node"], {"shop": ("размер",), "office": ()})
        self.assertEqual([question["id"] for question in reply["questions"]], ["plans.target_methods.0.protocol"])

        done = self.send("SFTP", {"plans.target_methods.0.protocol": "SFTP"})
        result = done["result"]
        self.assertEqual((result["status"], result["rules_count"], result["file_users_count"]), ("completed", 4, 2))
        file_rules = {rule["from"]: rule for rule in result["rules"] if rule["type"] == "file"}
        self.assertEqual(file_rules["office"]["checks_by_node"], {"office": ("маска имени",), "shop": ()})
        self.assertEqual(file_rules["shop"]["checks_by_node"], {"shop": ("размер",), "office": ()})
        self.assertEqual(self.llm.chat.call_count, 1)

    def test_access_no_in_batch_keeps_other_confirmed_fields(self):
        incomplete = {**FILES, "source_methods": None, "target_methods": None,
                      "access_group": None, "description": "Обновления"}
        self.start(LOGS, incomplete)
        reply = self.send("Любой текст видимой карточки", {
            "files.source_methods": "USB", "files.target_methods": "Автоматически в хранилище",
            "files.access_group": "Нет", "files.source_checks": "Без проверок",
            "files.target_checks": "Без проверок", "manual_users_count": "два",
        })
        current = server.sessions[self.session_id]
        self.assertEqual(current.manual_users_count, 2)
        self.assertEqual(current.flows[-1].source_methods[0].mode, "USB")
        self.assertIn("files.access_groups", [question["id"] for question in reply["questions"]])
        self.send("Отложить группы", {"files.access_groups": "Не знаю"})
        self.assertIn("files.access_groups", self.result["unknowns"])
        self.assertEqual(self.result["rules_count"], 1)
        self.assertEqual(sum(call.kwargs["purpose"] == "extract" for call in self.llm.chat.call_args_list), 1)

    def test_separate_access_group_names_create_two_file_rules(self):
        incomplete = {**FILES, "target_methods": [{"mode": "manual", "protocol": "SFTP"}],
                      "source_checks": [], "target_checks": [], "access_group": None}
        self.start(incomplete)
        self.send("Нет", {"files.access_group": "Нет"})
        answer = self.send("Две группы", {"files.access_groups": "Склад, Продажи", "manual_users_count": "два"})
        self.assertEqual(answer["result"]["status"], "completed")
        self.assertEqual(answer["result"]["rules_count"], 2)
        self.assertEqual(answer["result"]["file_users_count"], 2)

    def test_no_external_av_leaves_file_checks_unconfirmed(self):
        self.send("Отправляем журналы по UDP 514, обновления проверяем встроенным антивирусом.")
        self.script({"networks": NETWORKS, "flows": [
            LOGS, {**FILES, "source_checks": [], "target_checks": ["ICAP: внешний антивирус"]},
        ]})
        reply = self.send("его нет")
        self.assertEqual(reply["result"]["rules_count"], 1)
        self.assertTrue({"files.source_checks", "files.target_checks"} <= set(self.result["unknowns"]))

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
        values = {
            "files.source_checks": "Маска имени, Размер, Внешний антивирус",
            "files.target_checks": "Без проверок", "manual_users_count": "1",
        }
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
        self.assertIn("Офисная сеть — SFTP, вручную", done["explanation"])
        self.assertIn("Сеть цеха — SMB, автоматически", done["explanation"])
        self.assertEqual(done["result"]["file_users_count"], 1)
        self.assertIn("ICAP: внешний антивирус", done["explanation"])
        self.assertNotIn("{", done["explanation"])
        self.assertEqual(done["result"]["rules_count"], 1)
        self.assertEqual([c.kwargs["purpose"] for c in self.llm.chat.call_args_list], ["extract"])

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


    def test_generated_reply_preserves_core_questions_and_answer_binding(self):
        server.MODEL_WORDING_ENABLED = True
        self.script(
            {"networks": NETWORKS, "flows": [
                {**LOGS, "port": None},
                {**CONTROL, "port": None},
                {**LOGS, "id": "archive", "recipient": "Архив смены", "port": None},
            ]},
            {"text": "Для журналов и опроса контроллера пока не хватает портов получателей.",
             "questions": [{"id": "extra.checks", "text": "Какой антивирус нужно установить?"}]},
            {"text": "Порты согласованы. Получилось 3 правила для опроса ПЛК и журналов."},
        )
        message = "Настрой обмен журналами с двумя серверами и добавь опрос ПЛК."
        initial = self.send(message)
        by_id = {item["id"]: item for item in initial["questions"]}
        self.assertEqual(set(by_id), {"logs.port", "control.port", "archive.port"})
        self.assertIn("«Сервер журналов»", by_id["logs.port"]["text"])
        self.assertEqual(by_id["logs.port"]["options"], [])
        self.assertIn("портов получателей", initial["text"])

        self.result = None
        restored = self.send(message)
        self.assertEqual(restored["questions"], initial["questions"])
        values = {"logs.port": 1514, "control.port": 502, "archive.port": 2514}
        batch = "\n".join(f"{q['text']} {values[q['id']]}" for q in restored["questions"])
        done = self.send(batch)
        self.assertIn("Порты согласованы", done["text"])
        self.assertEqual(self.rules(), [("UDP", 1514), ("Modbus TCP", 502), ("UDP", 2514)])
        self.assertEqual([call.kwargs["purpose"] for call in self.llm.chat.call_args_list],
                         ["extract", "reply_wording", "reply_wording"])

    def test_generated_reply_explains_accepted_edit_and_rejects_invented_port(self):
        self.start(CONTROL)
        server.MODEL_WORDING_ENABLED = True
        self.script({"text": "У опроса ПЛК новый порт 1502 вместо 502. В схеме по-прежнему одно правило."},
                    {"text": "Порт 7777 установлен, опрос ПЛК теперь идёт через HTTPS."})
        edited = self.send("Поменяй порт у ПЛК линии на 1502")
        self.assertIn("новый порт 1502 вместо 502", edited["text"])
        self.assertEqual(self.rules(), [("Modbus TCP", 1502)])
        rejected = self.send("Поменяй порт у ПЛК линии на 70000")
        self.assertTrue(rejected["result_unchanged"])
        self.assertIn("65535", rejected["text"])
        self.assertNotIn("7777", rejected["text"])
        self.assertEqual(self.rules(), [("Modbus TCP", 1502)])

    def test_generated_storage_confirmation_keeps_final_rule_count(self):
        updates = {**FILES, "source_methods": [{"mode": "USB"}], "target_methods": [{"mode": "PUSH"}],
                   "source_checks": [], "target_checks": [], "description": "Обновления в цех"}
        self.script({"networks": NETWORKS, "manual_file_users": ["Оператор"], "flows": [{**LOGS, "port": 514}, updates]})
        self.send("Передаём журналы и обновления между сетями.")
        server.MODEL_WORDING_ENABLED = True
        self.script({"text": "Хранилище использует протокол SMB, а именно файловый сервер."})
        done = self.send("Хранилище согласовано", {
            "files.target_methods.0.protocol": "SMB", "files.target_methods.0.storage": "файловый сервер",
        })
        self.assertEqual((done["result"]["status"], done["result"]["rules_count"]), ("completed", 2))
        self.assertIn("1 → 2", done["text"])
        self.assertIn("файловый сервер", done["text"])

    def test_generated_reply_does_not_expose_internal_status_or_slots(self):
        server.MODEL_WORDING_ENABLED = True
        self.script({"networks": NETWORKS, "flows": [{**LOGS, "port": None}]},
                    {"text": 'Проект находится в состоянии "needs_clarification" (rules_count = 0).'})
        reply = self.send("Отправляем журналы в офис.")
        self.assertFalse(reply["result"]["rules_count"])
        self.assertNotIn("needs_clarification", reply["text"])
        self.assertNotIn("rules_count", reply["text"])

    def test_detailed_explanation_is_read_only(self):
        self.start(LOGS, CONTROL)
        server.MODEL_WORDING_ENABLED = True
        before = server.sessions[self.session_id]
        self.script({"text": (
            "Журналы идут на «Сервер журналов» по UDP 1514 в одну сторону. "
            "Опрос ПЛК использует Modbus TCP 502 и требует ответа."
        )})
        reply = self.send("Сравни правила для журналов и опроса ПЛК.")
        self.assertTrue(reply["result_unchanged"])
        self.assertTrue(reply["text"].startswith("Журналы идут"))
        self.assertIs(server.sessions[self.session_id], before)
        self.assertEqual(self.rules(), [("UDP", 1514), ("Modbus TCP", 502)])
        self.assertEqual(self.llm.chat.call_args.kwargs["purpose"], "reply_wording")

    def test_detailed_explanation_discards_unknown_protocol_or_port(self):
        self.start(LOGS)
        server.MODEL_WORDING_ENABLED = True
        self.script({"text": "Доставка журналов работает через HTTPS на 18888, получатель подтверждён."})
        reply = self.send("Объясни подробно правило для журналов.")
        self.assertTrue(reply["result_unchanged"])
        self.assertNotIn("18888", reply["text"])
        self.assertIn("UDP 1514", reply["text"])

    def test_detailed_explanation_rejects_ports_swapped_between_protocols(self):
        self.start(LOGS, CONTROL)
        server.MODEL_WORDING_ENABLED = True
        self.script({"text": "Журналы передаются по UDP 502, а диспетчер использует Modbus TCP 1514."})
        reply = self.send("Объясни подробно оба правила.")
        self.assertIn("UDP 1514", reply["text"])
        self.assertIn("Modbus TCP 502", reply["text"])
        self.assertNotIn("UDP 502", reply["text"])

    def test_optional_model_failure_returns_the_computed_summary(self):
        server.MODEL_WORDING_ENABLED = True
        self.start(LOGS)
        self.llm.chat.side_effect = GroqRateLimit(60)
        reply = self.send("Объясни подробно правило для журналов.")
        self.assertTrue(reply["result_unchanged"])
        self.assertIn("Сервер журналов", reply["text"])
        self.assertEqual(self.rules(), [("UDP", 1514)])
