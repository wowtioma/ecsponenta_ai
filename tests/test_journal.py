"""Тесты журнала и расчёта стоимости (чистая логика, без сети)."""
import unittest

from llm.journal import CallRecord, Journal


def make_call(call_id, t_in, t_out, p_in=0.10, p_out=0.40, session="s1"):
    return CallRecord(
        session_id=session,
        turn_id=1,
        call_id=call_id,
        model_id="google/gemini-2.0-flash-001",
        purpose="test",
        input_tokens=t_in,
        output_tokens=t_out,
        prompt_price=p_in,
        completion_price=p_out,
        cost_input=t_in * p_in / 1e6,
        cost_output=t_out * p_out / 1e6,
        cost_total=(t_in * p_in + t_out * p_out) / 1e6,
    )


class TestJournal(unittest.TestCase):
    def test_session_cost(self):
        j = Journal()
        j.add(make_call("a", 10000, 2000))  # 0.0010 + 0.0008 = 0.0018
        j.add(make_call("b", 5000, 1000))   # 0.0005 + 0.0004 = 0.0009
        self.assertAlmostEqual(j.session_cost("s1"), 0.0018 + 0.0009, places=10)

    def test_no_double_add(self):
        j = Journal()
        self.assertTrue(j.add(make_call("a", 1000, 100)))
        self.assertFalse(j.add(make_call("a", 1000, 100)))  # тот же call_id
        self.assertEqual(len(j.calls("s1")), 1)

    def test_model_breakdown(self):
        j = Journal()
        j.add(make_call("a", 1000, 100))
        j.add(make_call("b", 2000, 200))
        b = j.model_breakdown("s1")
        m = b["google/gemini-2.0-flash-001"]
        self.assertEqual(m["calls"], 2)
        self.assertEqual(m["input_tokens"], 3000)

    def test_export(self):
        j = Journal()
        j.add(make_call("a", 1000, 100))
        self.assertIn("call_id", j.export_jsonl("s1"))
        self.assertIn("cost_total", j.export_csv("s1"))


if __name__ == "__main__":
    unittest.main()
