from unittest import TestCase
from unittest.mock import Mock, patch

import httpx
from openai import OpenAI, RateLimitError

from llm.client import GroqRateLimit, LLMClient
from llm.journal import Journal
from llm.report import build_usage


class GroqRateLimitTests(TestCase):
    def test_cooldown_stops_requests_until_retry_after(self):
        with patch("llm.client.config.active_provider", return_value="groq"), patch(
            "llm.client.config.resolve_endpoint", return_value=("https://example.test", "test-model", "test-key")
        ):
            llm = LLMClient(Journal(), api_key="test-key")
        sdk = Mock()
        request = httpx.Request("POST", "https://example.test/chat/completions")
        sdk.chat.completions.create.side_effect = [
            RateLimitError(
                "limited", response=httpx.Response(429, headers={"retry-after": "17"}, request=request),
                body=None,
            ),
            "response",
        ]
        with patch("llm.client.time.monotonic", return_value=100) as clock:
            with self.assertRaises(GroqRateLimit) as initial:
                llm._complete(sdk)
            self.assertEqual(initial.exception.retry_after, 17)
            clock.return_value = 105
            with self.assertRaises(GroqRateLimit) as waiting:
                llm._complete(sdk)
            self.assertEqual(waiting.exception.retry_after, 12)
            self.assertEqual(sdk.chat.completions.create.call_count, 1)
            clock.return_value = 117
            self.assertEqual(llm._complete(sdk), "response")
        self.assertEqual(sdk.chat.completions.create.call_count, 2)

    def client_with_keys(self):
        with patch("llm.client.config.active_provider", return_value="groq"), patch(
            "llm.client.config.resolve_endpoint", return_value=("https://example.test", "test-model", "first")
        ), patch("llm.client.config.groq_keys", return_value=("first", "second", "third")):
            return LLMClient(Journal())

    @staticmethod
    def limited(seconds):
        request = httpx.Request("POST", "https://example.test/chat/completions")
        return RateLimitError("limited", response=httpx.Response(
            429, headers={"retry-after": str(seconds)}, request=request), body=None)

    def test_tries_each_key_and_reuses_the_successful_one(self):
        llm = self.client_with_keys()
        first, second, third = Mock(), Mock(), Mock()
        first.with_options.side_effect = lambda api_key: {"second": second, "third": third}[api_key]
        first.chat.completions.create.side_effect = self.limited(40)
        second.chat.completions.create.side_effect = self.limited(30)
        third.chat.completions.create.return_value = "ok"
        record = Mock()
        self.assertEqual(llm._complete(first, on_limit=record), "ok")
        self.assertEqual(llm._complete(first, on_limit=record), "ok")
        self.assertEqual(record.call_count, 2)
        self.assertEqual([s.chat.completions.create.call_count for s in (first, second, third)], [1, 1, 2])

    def test_all_keys_wait_for_earliest_reset(self):
        llm = self.client_with_keys()
        first, second, third = Mock(), Mock(), Mock()
        first.with_options.side_effect = lambda api_key: {"second": second, "third": third}[api_key]
        for client, delay in zip((first, second, third), (90, 12, 30)):
            client.chat.completions.create.side_effect = self.limited(delay)
        with patch("llm.client.time.monotonic", return_value=100) as clock:
            for _ in range(2):
                with self.assertRaises(GroqRateLimit) as exc:
                    llm._complete(first)
                self.assertEqual(exc.exception.retry_after, 12)
            clock.return_value = 112
            second.chat.completions.create.side_effect = None
            second.chat.completions.create.return_value = "ok"
            self.assertEqual(llm._complete(first), "ok")
        self.assertEqual([s.chat.completions.create.call_count for s in (first, second, third)], [1, 2, 1])

    def test_unrelated_error_is_not_retried(self):
        llm = self.client_with_keys()
        first = Mock()
        first.chat.completions.create.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            llm._complete(first)
        first.with_options.assert_not_called()

    def test_preferred_slot_wraps_and_duplicate_keys_are_skipped(self):
        from llm.config import groq_keys
        with patch.dict("os.environ", {"GROQ_ACTIVE_SLOT": "3", "GROQ_API_KEY_3": "c",
                                       "GROQ_API_KEY_1": "a", "GROQ_API_KEY_2": "c"}, clear=True):
            self.assertEqual(groq_keys(), ("c", "a"))

    def test_sdk_retries_same_payload_and_reports_both_attempts(self):
        llm = self.client_with_keys()
        requests = []

        def respond(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(429, headers={"Retry-After": "30"}, json={"error": {"message": "limit"}})
            return httpx.Response(200, json={
                "id": "completion-1", "object": "chat.completion", "created": 1, "model": "test-model",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
            })

        with httpx.Client(transport=httpx.MockTransport(respond)) as http:
            llm._client = OpenAI(base_url="https://example.test", api_key="first", http_client=http, max_retries=0)
            with patch("llm.client.config.billable_tariff", return_value=("test-model", 0.075, 0.30)):
                answer, _ = llm.chat([{"role": "user", "content": "ping"}], session_id="s", turn_id=1)
        self.assertEqual(answer, "ok")
        self.assertEqual([r.headers["Authorization"] for r in requests], ["Bearer first", "Bearer second"])
        self.assertEqual(requests[0].content, requests[1].content)
        usage = build_usage(llm.journal, "s")
        statuses = {c["status"]: c for c in usage["calls"]}
        self.assertEqual([c["status"] for c in usage["calls"]], ["rate_limited", "ok"])
        self.assertIsNone(statuses["rate_limited"]["cost_total_usd"])
        self.assertEqual((usage["status"], usage["input_tokens"], usage["output_tokens"]), ("partial", 8, 2))
