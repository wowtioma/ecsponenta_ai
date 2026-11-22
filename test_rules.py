"""Semantic checks from the public scenario descriptions; no benchmark fixtures."""

import unittest

from rules import Session, evaluate


NETWORKS = [
    {"id": "open", "name": "Office", "kind": "open"},
    {"id": "closed", "name": "Plant", "kind": "closed"},
]


def data(id, origin, protocol, port, recipient=None, initiator=None):
    return {
        "id": id,
        "source_network_id": origin,
        "target_network_id": "closed" if origin == "open" else "open",
        "payload": "data",
        "direction": "one_way",
        "protocol": protocol,
        "port": port,
        "recipient": recipient,
        "initiator_network_id": initiator,
    }


def files(origin_method, checks):
    return {
        "id": "files",
        "source_network_id": "open",
        "target_network_id": "closed",
        "payload": "files",
        "direction": "one_way",
        "source_methods": [{"mode": origin_method}],
        "target_methods": [{"mode": "PUSH", "protocol": "SMB", "storage": "plant-storage"}],
        "source_checks": checks,
        "target_checks": [],
        "access_group": "shared",
    }


def calculate(flows, **kwargs):
    state = Session(session_id="public-example", networks=NETWORKS, flows=flows, **kwargs)
    return evaluate(state)["result"]


class PublicScenarioTests(unittest.TestCase):
    def test_f01(self):
        result = calculate([data(f"log-{i}", "closed", "UDP", 514, "monitor") for i in range(3)])
        self.assertEqual(result["rules_count"], 1)
        self.assertEqual(result["file_users_count"], 0)
        self.assertEqual(self.signatures(result), [("closed", "open", "one-way", "UDP", 514)])

    def test_f02(self):
        result = calculate([
            data("poll", "open", "Modbus TCP", 502, "controller", "open"),
            data("logs", "closed", "UDP", 514, "monitor"),
            data("time", "open", "NTP", 123),
        ])
        self.assertEqual(result["rules_count"], 3)
        self.assertEqual(self.signatures(result), [
            ("open", "closed", "two-way", "Modbus TCP", 502),
            ("closed", "open", "one-way", "UDP", 514),
            ("open", "closed", "one-way", "UDP", 123),
        ])
        self.assertEqual(result["file_users_count"], 0)

    def test_f04(self):
        result = calculate([files("manual", ["name mask", "size", "ICAP AV"])], manual_file_users=["engineer"])
        self.assertEqual(result["rules_count"], 1)
        self.assertEqual(result["file_users_count"], 1)
        rule = result["rules"][0]
        self.assertEqual((rule["from"], rule["to"], rule["mode"]), ("open", "closed", "one-way"))
        self.assertEqual(rule["protocol"], {"open": "SFTP, вручную", "closed": "SMB, автоматически"})

    def test_f07(self):
        result = calculate([
            data("mqtt", "closed", "MQTT", None, "office-broker", "closed"),
            data("time", "open", "NTP", 123),
            files("USB", ["ICAP AV"]),
        ], manual_file_users=["contractor"], unknown_answers=["mqtt.port"])
        self.assertEqual(result["rules_count"], 3)
        self.assertEqual(self.signatures(result), [
            ("closed", "open", "two-way", "MQTT", None),
            ("open", "closed", "one-way", "UDP", 123),
        ])
        self.assertEqual(result["file_users_count"], 1)
        self.assertEqual(result["status"], "preliminary")
        self.assertIn("mqtt.port", result["unknowns"])
        self.assertEqual(result["synonyx"]["node_a_faces"], "open")
        self.assertEqual(result["rules"][2]["protocol"]["open"], "USB-носитель на Узле А")
        self.assertEqual(result["rules"][2]["protocol"]["closed"], "SMB, автоматически")

    @staticmethod
    def signatures(result):
        return [
            (rule["from"], rule["to"], rule["mode"], rule["protocol"], rule["port"])
            for rule in result["rules"] if rule["type"] == "data"
        ]


if __name__ == "__main__":
    unittest.main()
