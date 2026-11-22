"""Тесты нормализации слотов под модель участка A (без сети)."""
import unittest

from llm.extract import _normalize_flows


NETWORKS = [
    {"id": "open", "name": "Офис", "trust": "open"},
    {"id": "closed", "name": "Цех", "trust": "closed"},
]


class TestNormalizeFlows(unittest.TestCase):
    def _data(self, flows, networks=None):
        return {"networks": networks or [dict(n) for n in NETWORKS], "flows": flows}

    def test_explicit_usb_and_smb_repair_a_same_network_extraction(self):
        data = self._data([{"type": "file", "from": "closed", "to": "closed",
                            "source_methods": [{"mode": "manual", "protocol": "SFTP"}]}])
        _normalize_flows(data, "Обновления приносит подрядчик на флешке. После проверки внешним "
                               "антивирусом они должны автоматически попадать на файловый сервер цеха по SMB, "
                               "из цеха на флешку ничего не выгружается.")
        flow = data["flows"][0]
        self.assertEqual((flow["from"], flow["to"]), ("open", "closed"))
        self.assertEqual(flow["source_methods"][0]["mode"], "USB")
        self.assertEqual(flow["target_methods"][0]["protocol"], "SMB")

    def test_port_validation(self):
        d = self._data([{"port": "502"}, {"port": 99999}, {"port": "abc"}, {"port": 0}])
        _normalize_flows(d)
        self.assertEqual([f["port"] for f in d["flows"]], [502, None, None, None])

    def test_network_refs(self):
        d = self._data([{"from": "closed", "to": "nonexistent", "initiator_network_id": "zzz"}])
        _normalize_flows(d)
        f = d["flows"][0]
        self.assertEqual(f["from"], "closed")
        self.assertIsNone(f["to"])
        # инициатор восстановлен из from
        self.assertEqual(f["initiator_network_id"], "closed")

    def test_methods_normalization(self):
        d = self._data(
            [
                {
                    "source_methods": [{"mode": "usb"}, {"mode": "pull", "protocol": "sftp"}],
                    "target_methods": [{"mode": "push", "protocol": "smb", "trigger": "arrival"}],
                }
            ]
        )
        _normalize_flows(d)
        f = d["flows"][0]
        self.assertEqual(f["source_methods"][0]["mode"], "USB")
        self.assertEqual(f["source_methods"][1]["mode"], "PULL")
        self.assertEqual(f["source_methods"][1]["protocol"], "SFTP")
        self.assertEqual(f["target_methods"][0]["mode"], "PUSH")
        self.assertEqual(f["target_methods"][0]["trigger"], "arrival")

    def test_invalid_methods_dropped(self):
        d = self._data([{"source_methods": [{"mode": "teleport"}, "junk"]}])
        _normalize_flows(d)
        self.assertIsNone(d["flows"][0]["source_methods"])

    def test_checks_normalization(self):
        d = self._data([{"source_checks": "ICAP:антивирус", "target_checks": []}])
        _normalize_flows(d)
        f = d["flows"][0]
        self.assertEqual(f["source_checks"], ["ICAP: внешний антивирус"])
        # [] означает «явно без проверок» (не None)
        self.assertEqual(f["target_checks"], [])

    def test_missing_check_side_stays_unknown(self):
        d = self._data([{"source_checks": ["маска имени"], "target_checks": None}])
        _normalize_flows(d)
        f = d["flows"][0]
        self.assertEqual(f["source_checks"], ["маска имени"])
        self.assertIsNone(f["target_checks"])

    def test_english_checks_canonicalized(self):
        d = self._data([{"source_checks": ["mask name", "size", {"type": "ICAP:антивирус"}]}])
        _normalize_flows(d)
        self.assertEqual(
            d["flows"][0]["source_checks"],
            ["маска имени", "размер", "ICAP: внешний антивирус"],
        )

    def test_usb_flow_direction(self):
        d = self._data(
            [{"type": "file", "from": "closed", "to": "closed",
              "source_methods": [{"mode": "usb"}]}]
        )
        _normalize_flows(d)
        f = d["flows"][0]
        self.assertEqual((f["from"], f["to"]), ("open", "closed"))

    def test_same_network_flow_retained_for_validation(self):
        d = self._data([{"from": "closed", "to": "closed"}])
        _normalize_flows(d)
        self.assertEqual(d["flows"][0]["from"], d["flows"][0]["to"])

    def test_manual_users_from_text(self):
        d = self._data(
            [{"type": "file", "from": "open", "to": "closed",
              "source_methods": [{"mode": "usb"}]}]
        )
        _normalize_flows(d, "Обновления приносит подрядчик на флешке.")
        self.assertEqual(d["manual_file_users"], ["подрядчик"])

    def test_top_level_bonus_fields(self):
        d = self._data([])
        d["manual_file_users"] = "подрядчик"
        d["requests_for_vendor"] = ["встроенный антивирус"]
        _normalize_flows(d)
        self.assertEqual(d["manual_file_users"], ["подрядчик"])
        self.assertEqual(d["requests_for_vendor"], ["встроенный антивирус"])

    def test_defaults_present(self):
        d = self._data([{}])
        _normalize_flows(d)
        f = d["flows"][0]
        for key in (
            "recipient",
            "application_protocol",
            "reverse_forbidden",
            "source_methods",
            "target_methods",
            "source_checks",
            "target_checks",
            "access_group",
        ):
            self.assertIn(key, f)
        self.assertIsNone(d["manual_file_users"])
        self.assertEqual(d["requests_for_vendor"], [])


if __name__ == "__main__":
    unittest.main()
