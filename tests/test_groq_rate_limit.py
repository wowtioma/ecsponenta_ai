from unittest import TestCase
from unittest.mock import Mock, patch

import httpx
from openai import RateLimitError

from llm.client import GroqRateLimit, LLMClient
from llm.journal import Journal


class GroqRateLimitTests(TestCase):
    def test_cooldown_stops_requests_until_retry_after(self):
        with patch("llm.client.config.active_provider", return_value="groq"), patch(
            "llm.client.config.resolve_endpoint", return_value=("https://example.test", "test-model", "test-key")
        ):
            llm = LLMClient(Journal())
        sdk = Mock()
        request = httpx.Request("POST", "https://example.test/chat/completions")
        sdk.chat.completions.create.side_effect = [
            RateLimitError(
                "limited", response=httpx.Response(429, headers={"retry-after": "17"}, request=request),
                body=None,
            ),
            "response",
        ]
        with patch("llm.client.time.monotonic", side_effect=[100, 100, 105, 117]):
            with self.assertRaises(GroqRateLimit) as initial:
                llm._complete(sdk)
            self.assertEqual(initial.exception.retry_after, 17)
            with self.assertRaises(GroqRateLimit) as waiting:
                llm._complete(sdk)
            self.assertEqual(waiting.exception.retry_after, 12)
            self.assertEqual(sdk.chat.completions.create.call_count, 1)
            self.assertEqual(llm._complete(sdk), "response")
        self.assertEqual(sdk.chat.completions.create.call_count, 2)
