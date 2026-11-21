"""Тесты сбора потребностей для разработчика (бонус §12.7)."""
import unittest

from llm.vendor import VendorRequests, detect_unsupported


class TestDetectUnsupported(unittest.TestCase):
    def test_builtin_av_inflection(self):
        for t in ["встроенный антивирус", "встроенным антивирусом", "встроенного антивируса"]:
            self.assertTrue(detect_unsupported(t), f"не поймано: {t}")

    def test_external_av_not_flagged(self):
        self.assertEqual(detect_unsupported("проверить антивирусом по ICAP"), [])

    def test_routing(self):
        self.assertTrue(detect_unsupported("открой доступ на подсеть"))

    def test_o01_benchmark(self):
        q = "Пусть Синоникс сам проверяет файлы встроенным антивирусом."
        found = detect_unsupported(q)
        self.assertTrue(any("антивирус" in f for f in found))


class TestVendorRequests(unittest.TestCase):
    def test_scan_and_list(self):
        v = VendorRequests("s1")
        v.scan("нужен встроенный антивирус", turn_id=1)
        v.add("хочу три сети", kind="other", turn_id=2)
        lst = v.to_list()
        self.assertTrue(any("антивирус" in x for x in lst))
        self.assertIn("хочу три сети", lst)

    def test_empty(self):
        self.assertEqual(VendorRequests().to_list(), [])


if __name__ == "__main__":
    unittest.main()
