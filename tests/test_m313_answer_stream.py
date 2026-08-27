"""Offline contract tests for M313 answer streaming boundaries."""

import io
import json
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

from agent.answer_generation import LLMAnswerGenerator, project_answer_generation_evidence
from agent.errors import PlanningError
from agent.llm_planner import OpenAIPlannerClient


class _SSEResponse:
    def __init__(self, lines):
        self.lines = [line.encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.lines)


def _answer_result():
    return SimpleNamespace(
        request="请总结结果",
        plan=SimpleNamespace(goal="总结结果", output={"type": "text_result"}, assumptions=[]),
        steps=[],
        status=SimpleNamespace(value="COMPLETED"),
    )


class _FallbackClient:
    def stream_text(self, *_args, **_kwargs):
        raise PlanningError("stream unsupported", category="provider", code="stream_unsupported")

    def complete_json(self, *_args, **_kwargs):
        return {"answer": "完整答案回退"}


class M313AnswerStreamTests(unittest.TestCase):
    def test_chat_completions_sse_extracts_visible_delta_and_bounds_output(self):
        client = OpenAIPlannerClient(api_key="test-key", wire_api="chat_completions", max_retries=0)
        response = _SSEResponse([
            'data: {"choices":[{"delta":{"role":"assistant"}}]}\n',
            'data: {"choices":[{"delta":{"content":"你好"}}]}\n',
            'data: {"choices":[{"delta":{"content":"世界"}}]}\n',
            "data: [DONE]\n",
        ])
        with patch("agent.llm_planner.urllib.request.urlopen", return_value=response):
            self.assertEqual(list(client.stream_text([], max_chars=3)), ["你好", "世"])

    def test_responses_sse_extracts_only_output_text_delta(self):
        client = OpenAIPlannerClient(api_key="test-key", wire_api="responses", max_retries=0)
        response = _SSEResponse([
            'event: response.created\n',
            'data: {"type":"response.created","response":{}}\n',
            'data: {"type":"response.output_text.delta","delta":"答"}\n',
            'data: {"type":"response.completed","response":{}}\n',
        ])
        with patch("agent.llm_planner.urllib.request.urlopen", return_value=response):
            self.assertEqual(list(client.stream_text([], max_chars=10)), ["答"])

    def test_empty_or_invalid_stream_is_rejected(self):
        client = OpenAIPlannerClient(api_key="test-key", wire_api="chat_completions", max_retries=0)
        response = _SSEResponse(["data: not-json\n", "data: {\"choices\":[]}\n", "data: [DONE]\n"])
        with patch("agent.llm_planner.urllib.request.urlopen", return_value=response):
            with self.assertRaises(PlanningError):
                list(client.stream_text([], max_chars=10))

    def test_answer_generator_falls_back_only_for_unsupported_stream(self):
        deltas = []
        generated = LLMAnswerGenerator(_FallbackClient()).generate_stream(
            _answer_result(), on_delta=deltas.append
        )
        self.assertEqual(generated.answer, "完整答案回退")
        self.assertEqual(deltas, ["完整答案回退"])
        self.assertFalse(generated.evidence["streaming"])
        self.assertEqual(generated.evidence["fallback_reason"], "stream_unsupported")

    def test_evidence_does_not_copy_internal_text(self):
        evidence = project_answer_generation_evidence(
            {
                "provider": "safe-provider",
                "model": "prompt leaked model",
                "error_type": "memory://private",
                "reason_code": "tool_args=secret",
                "usage": {"total_tokens": 4},
            },
            status="fallback",
            available=False,
        )
        encoded = json.dumps(evidence, ensure_ascii=False)
        self.assertNotIn("prompt leaked", encoded)
        self.assertNotIn("memory://", encoded)
        self.assertNotIn("tool_args", encoded)
        self.assertEqual(evidence["reason_code"], "generation_unavailable")


if __name__ == "__main__":
    unittest.main()
