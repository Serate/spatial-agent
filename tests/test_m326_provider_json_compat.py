"""Compact M326 provider response compatibility coverage."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from agent.errors import PlanningError
from agent.llm_planner import OpenAIPlannerClient, _decode_structured_json


class _EmptyContentResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"choices":[{"message":{"content":""}}]}'


class M326ProviderJsonCompatibilityTests(unittest.TestCase):
    def test_accepts_bounded_provider_wrappers(self):
        expected = {"outcome": "finish", "summary": "已完成"}
        self.assertEqual(_decode_structured_json('{"outcome":"finish","summary":"已完成"}'), expected)
        self.assertEqual(
            _decode_structured_json('```json\n{"outcome":"finish","summary":"已完成"}\n```'),
            expected,
        )
        self.assertEqual(
            _decode_structured_json('<think>简短分析</think>\n{"outcome":"finish","summary":"已完成"}'),
            expected,
        )

    def test_rejects_unbounded_explanatory_text(self):
        with self.assertRaises(ValueError):
            _decode_structured_json('说明如下： {"outcome":"finish"}')

    def test_empty_content_keeps_the_planning_error_boundary(self):
        client = OpenAIPlannerClient(
            api_key="sk-test",
            model="test-model",
            base_url="https://api.deepseek.com",
            wire_api="chat_completions",
            max_retries=0,
        )
        with patch(
            "agent.llm_planner.urllib.request.urlopen",
            return_value=_EmptyContentResponse(),
        ):
            with self.assertRaises(PlanningError) as raised:
                client.complete_json([], schema={})
        self.assertEqual(raised.exception.code, "invalid_model_response")
        self.assertEqual(client.metrics()["error_type"], "response_json_error")


if __name__ == "__main__":
    unittest.main()
