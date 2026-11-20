"""Тесты regex-фолбэка извлечения (без LLM, без сети)."""
import unittest

from llm.extract import quick_extract


F02 = (
    "Насосная станция водоканала работает в отдельной закрытой сети. Диспетчер "
    "сидит в общей сети водоканала. Программа диспетчера опрашивает контроллер "
    "насосов по Modbus TCP, порт 502. Компьютер оператора станции отправляет "
    "журналы событий на сервер мониторинга в общей сети по UDP 514, обратно "
    "ничего. Сервер времени из общей сети передаёт точное время по NTP, это UDP 123."
)


class TestQuickExtract(unittest.TestCase):
    def test_protocols_and_port(self):
        r = quick_extract(F02)
        protos = [f["protocol"] for f in r["flows"]]
        self.assertIn("Modbus TCP", protos)
        self.assertIn("UDP", protos)
        ports = [f["port"] for f in r["flows"] if f["port"] is not None]
        self.assertIn(502, ports)

    def test_networks_detected(self):
        r = quick_extract(F02)
        trusts = [n["trust"] for n in r["networks"]]
        self.assertIn("closed", trusts)
        self.assertIn("open", trusts)

    def test_file_type_detected(self):
        text = "Инженер в офисе вручную передаёт файлы программ по SFTP, проверять антивирусом."
        r = quick_extract(text)
        sftp = [f for f in r["flows"] if f["protocol"] == "SFTP"]
        self.assertTrue(sftp)
        self.assertEqual(sftp[0]["type"], "file")


if __name__ == "__main__":
    unittest.main()
