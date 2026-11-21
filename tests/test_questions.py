"""Тесты генерации формулировок уточняющих вопросов (без сети)."""
import json
import unittest

from llm.questions import REQUIRED_OPTIONS, ensure_options, rephrase_questions


class FakeClient:
    """Заглушка LLMClient: возвращает заранее заданный ответ или падает."""

    def __init__(self, reply=None, raise_error=None):
        self.reply = reply
        self.raise_error = raise_error
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.raise_error is not None:
            raise self.raise_error
        return self.reply, None


QUESTIONS = [
    {"id": "flow-1.port", "text": "Какой порт принимает соединение?",
     "options": ["Не знаю", "Другое"]},
    {"id": "flow-1.recipient", "text": "Сколько систем принимают данные и какие?",
     "options": ["Одна система", "Несколько систем"]},
]


class TestEnsureOptions(unittest.TestCase):
    def test_adds_missing_tails(self):
        q = ensure_options({"id": "x", "options": ["TCP", "UDP"]})
        self.assertEqual(q["options"][-2:], list(REQUIRED_OPTIONS))

    def test_no_duplicates(self):
        q = ensure_options({"id": "x", "options": ["TCP", "Не знаю", "Другое"]})
        self.assertEqual(q["options"].count("Не знаю"), 1)
        self.assertEqual(q["options"].count("Другое"), 1)

    def test_case_insensitive(self):
        q = ensure_options({"id": "x", "options": ["не знаю", "другое"]})
        self.assertEqual(len(q["options"]), 2)


class TestRephrase(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(rephrase_questions(None, []), [])

    def test_no_client_passthrough(self):
        result = rephrase_questions(None, QUESTIONS, "текст")
        self.assertEqual([q["id"] for q in result], [q["id"] for q in QUESTIONS])
        # обязательные варианты добавлены, даже без LLM
        self.assertIn("Не знаю", result[1]["options"])

    def test_replaces_text_keeps_id_and_options(self):
        reply = json.dumps(
            {
                "questions": [
                    {"id": "flow-1.port", "text": "На каком порту контроллер насосов слушает Modbus?"},
                    # второй вопрос не вернули — должен сохранить текст A
                ]
            },
            ensure_ascii=False,
        )
        result = rephrase_questions(FakeClient(reply), QUESTIONS, "опрос контроллера")
        self.assertEqual(result[0]["text"], "На каком порту контроллер насосов слушает Modbus?")
        self.assertEqual(result[0]["id"], "flow-1.port")
        self.assertEqual(result[1]["text"], QUESTIONS[1]["text"])
        self.assertEqual(result[1]["options"], QUESTIONS[1]["options"] + ["Не знаю", "Другое"])

    def test_bad_json_falls_back(self):
        result = rephrase_questions(FakeClient("это не json"), QUESTIONS, "текст")
        self.assertEqual([q["text"] for q in result], [q["text"] for q in QUESTIONS])

    def test_llm_error_falls_back(self):
        result = rephrase_questions(
            FakeClient(raise_error=RuntimeError("boom")), QUESTIONS, "текст"
        )
        self.assertEqual([q["text"] for q in result], [q["text"] for q in QUESTIONS])

    def test_does_not_mutate_input(self):
        original = [dict(q) for q in QUESTIONS]
        rephrase_questions(None, QUESTIONS, "текст")
        self.assertEqual(QUESTIONS, original)


if __name__ == "__main__":
    unittest.main()
