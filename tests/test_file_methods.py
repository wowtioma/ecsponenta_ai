"""Страховки извлечения файловых потоков (без LLM и без сети).

Проверяем два случая из реального диалога:
- «вручную по SFTP» и «автоматически доставляет в хранилище по SMB/PUSH»;
- модель дорисовала обратный поток, хотя в тексте его нет.
"""
import unittest

from llm.extract import _drop_mirrored_flows, _rescue_methods


TEXT = (
    "Один инженер офиса вручную передаёт файлы по SFTP в закрытый сегмент; "
    "там устройство автоматически доставляет их в хранилище по SMB/PUSH. "
    "Требуются маска имени, проверка размера и внешний антивирус по ICAP."
)


class TestRescueMethods(unittest.TestCase):
    def test_manual_sftp_and_push_smb(self):
        flow = {
            "type": "file",
            "from": "open",
            "to": "closed",
            "source_methods": None,
            "target_methods": None,
        }

        _rescue_methods(TEXT, flow)

        self.assertEqual(flow["source_methods"][0]["mode"], "manual")
        self.assertEqual(flow["source_methods"][0]["protocol"], "SFTP")
        self.assertEqual(flow["target_methods"][0]["mode"], "PUSH")
        self.assertEqual(flow["target_methods"][0]["protocol"], "SMB")

    def test_data_flow_untouched(self):
        flow = {"type": "data", "source_methods": None, "target_methods": None}

        _rescue_methods(TEXT, flow)

        self.assertIsNone(flow["source_methods"])
        self.assertIsNone(flow["target_methods"])


class TestDropMirroredFlows(unittest.TestCase):
    def test_drop_invented_reverse_file_flow(self):
        flows = [
            {"type": "file", "from": "open", "to": "closed", "protocol": None, "port": None},
            {"type": "file", "from": "closed", "to": "open", "protocol": None, "port": None},
        ]

        self.assertEqual(len(_drop_mirrored_flows(flows, TEXT)), 1)

    def test_keep_when_reverse_is_explicit(self):
        text = TEXT + " Файлы также передаются обратно."
        flows = [
            {"type": "file", "from": "open", "to": "closed", "protocol": None, "port": None},
            {"type": "file", "from": "closed", "to": "open", "protocol": None, "port": None},
        ]

        self.assertEqual(len(_drop_mirrored_flows(flows, text)), 2)

    def test_keep_flows_with_different_protocols(self):
        flows = [
            {"type": "data", "from": "open", "to": "closed", "protocol": "TCP", "port": 502},
            {"type": "data", "from": "closed", "to": "open", "protocol": "UDP", "port": 514},
        ]

        self.assertEqual(len(_drop_mirrored_flows(flows, "опрос по TCP и журналы по UDP")), 2)


if __name__ == "__main__":
    unittest.main()
