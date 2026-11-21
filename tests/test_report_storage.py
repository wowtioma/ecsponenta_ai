"""Тесты отчёта usage/timing и сохранения журнала на диск (без сети)."""
import shutil
import unittest
from pathlib import Path

from llm.journal import CallRecord, Journal
from llm.report import build_timing, build_usage
from llm.storage import load_session, save_session


def make_call(call_id, t_in, t_out, session="s1", turn=1):
    p_in, p_out = 0.03, 0.14
    return CallRecord(
        session_id=session, turn_id=turn, call_id=call_id,
        model_id="openai/gpt-oss-20b", purpose="test",
        input_tokens=t_in, output_tokens=t_out,
        prompt_price=p_in, completion_price=p_out,
        cost_input=t_in * p_in / 1e6, cost_output=t_out * p_out / 1e6,
        cost_total=(t_in * p_in + t_out * p_out) / 1e6,
    )


class TestUsageTiming(unittest.TestCase):
    def test_usage_not_measured(self):
        j = Journal()
        self.assertEqual(build_usage(j, "s1")["status"], "not_measured")

    def test_usage_measured(self):
        j = Journal()
        j.add(make_call("a", 1000, 200))
        u = build_usage(j, "s1")
        self.assertEqual(u["status"], "measured")
        self.assertEqual(u["input_tokens"], 1000)
        self.assertEqual(u["output_tokens"], 200)
        self.assertGreater(u["evaluation_cost_usd"], 0)
        self.assertEqual(len(u["calls"]), 1)
        self.assertIn("call_id", u["calls"][0])

    def test_timing(self):
        j = Journal()
        j.add(make_call("a", 100, 100, turn=1))
        j.add(make_call("b", 100, 100, turn=1))
        t = build_timing(j, "s1")
        self.assertEqual(len(t["turns"]), 1)
        self.assertEqual(t["turns"][0]["calls"], 2)
        self.assertIsInstance(t["mean_turn_seconds"], float)


class TestStorage(unittest.TestCase):
    def test_roundtrip(self):
        j = Journal()
        j.add(make_call("a", 1000, 200))
        d = Path(__file__).parent / "_tmp_storage_test"
        d.mkdir(exist_ok=True)
        try:
            paths = save_session(j, "s1", data_dir=d)
            self.assertTrue(Path(paths["jsonl"]).exists())
            self.assertTrue(Path(paths["json"]).exists())
            data = load_session("s1", data_dir=d)
            self.assertEqual(data["session_id"], "s1")
            self.assertEqual(data["usage"]["input_tokens"], 1000)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
