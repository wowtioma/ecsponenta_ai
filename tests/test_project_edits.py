import unittest

from project_edits import continue_recipient_edit, edit_project
from rules import Flow, Network, Session, evaluate


class ProjectEditTests(unittest.TestCase):
    def setUp(self):
        self.session = Session(
            session_id="edit-test",
            networks=[
                Network(id="open", name="Диспетчерская", kind="open"),
                Network(id="closed", name="Насосная", kind="closed"),
            ],
            flows=[
                Flow(id="flow-1", payload="data", protocol="Modbus TCP", port=502,
                     source_network_id="open", target_network_id="closed",
                     initiator_network_id="open", recipient="Контроллер насосов"),
                Flow(id="flow-2", payload="data", protocol="UDP", port=514,
                     source_network_id="closed", target_network_id="open",
                     direction="one_way", recipient="Сервер журналов"),
            ],
        )

    def edit(self, message):
        return edit_project(self.session, message, client=None, turn_id=2)

    def test_controller_port_changes_only_the_selected_flow(self):
        updated, text = self.edit("поменять порт у контроллера на 515")
        self.assertEqual([rule["port"] for rule in evaluate(updated)["result"]["rules"]], [515, 514])
        self.assertEqual(updated.flows[1], self.session.flows[1])
        self.assertEqual(self.session.flows[0].port, 502)
        self.assertIn("502 → 515", text)

    def test_ambiguous_port_change_requests_target(self):
        updated, text, pending = self.edit("поменять порт на 515")
        self.assertIs(updated, self.session)
        self.assertIn("у какого потока", text)
        self.assertEqual(pending.port, 515)

    def test_invalid_and_repeated_port_changes_keep_state(self):
        for port, hint in [(65536, "65535"), (502, "уже указаны")]:
            with self.subTest(port=port):
                updated, text = self.edit(f"поменять порт у контроллера на {port}")
                self.assertIs(updated, self.session)
                self.assertIn(hint, text)


    def test_impossible_direction_is_rejected_for_modbus(self):
        from unittest.mock import Mock

        client = Mock()
        client.chat.return_value = ('{"flow_id":"flow-1","fields":{"direction":"one_way"}}', None)
        updated, text = edit_project(self.session, "сделай Modbus однонаправленным", client, 2)
        self.assertIs(updated, self.session)
        self.assertIn("требуется двунаправленное правило", text)


    def test_extra_recipient_inherits_protocol_even_when_named_ntp_server(self):
        from unittest.mock import Mock

        self.session.flows[0].source_device = "NTP-сервер"
        self.session.flows[0].recipient = "Сервер времени станции"
        client = Mock()
        client.chat.return_value = (
            '{"action":"add_recipient","flow_id":"flow-2","recipient":"Сервер времени станции","network_id":"closed"}',
            None,
        )
        updated, text, question = edit_project(self.session, "пусть журналы приходят еще на NTP-сервер", client, 2)

        self.assertEqual(updated.flows[:-1], self.session.flows)
        self.assertEqual(updated.flows[-1].recipient, "NTP-сервер")
        self.assertEqual(updated.flows[-1].protocol, "UDP")
        self.assertEqual(updated.flows[-1].port, 514)
        self.assertIn("UDP 514", text)
        self.assertEqual(evaluate(updated)["result"]["rules_count"], 3)

    def test_recipient_on_same_side_as_sender_is_rejected(self):
        from unittest.mock import Mock

        self.session.flows[0].recipient = "Резервный сервер"
        self.session.flows[1].source_device = "Контроллер насосов"
        client = Mock()
        client.chat.return_value = (
            '{"action":"add_recipient","flow_id":"flow-2","recipient":"Резервный сервер"}',
            None,
        )
        updated, text, question = edit_project(self.session, "пусть журналы идут ещё на резервный сервер", client, 2)

        self.assertIs(updated, self.session)
        self.assertIn("вне сети получателей", text)
        self.assertIsNotNone(question)
        same, rejected, active = continue_recipient_edit(self.session, question, "Контроллер насосов")
        self.assertIs(same, self.session)
        self.assertIn("Контроллер насосов", rejected)
        self.assertIsNotNone(active)
