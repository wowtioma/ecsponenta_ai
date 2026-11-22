"""Тесты поиска по базе знаний (без сети, читает реальную папку synonyx_base)."""
import unittest

from llm import rag


class TestKnowledgeBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = rag.KnowledgeBase()

    def test_index_not_empty(self):
        self.assertGreater(len(self.kb.sections), 0)

    def test_fact_256_rules(self):
        hits = self.kb.search("сколько правил можно настроить на одном Синониксе")
        self.assertTrue(hits)
        top = hits[0]
        self.assertIn("256", top["text"])
        self.assertTrue(top["file"])
        self.assertTrue(top["section"])

    def test_fact_no_builtin_antivirus(self):
        hits = self.kb.search("встроенный антивирус Синоникса")
        self.assertTrue(hits)
        combined = " ".join(h["text"] for h in hits)
        self.assertIn("нет", combined)
        # факт должен быть в справочнике 1.9
        self.assertTrue(any("01_scope_functions" in h["file"] for h in hits))

    def test_cite_format(self):
        hits = self.kb.search("межсетевой экран зачем нужен")
        self.assertTrue(hits)
        cite = self.kb.cite(hits[0])
        self.assertIn(".md", cite)
        self.assertIn("раздел", cite)


if __name__ == "__main__":
    unittest.main()
