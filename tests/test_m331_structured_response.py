"""M331-A compact conformance checks for model-shaped structured responses."""

from __future__ import annotations

import unittest

from agent.answer_generation import LLMAnswerGenerator
from agent.errors import PlanningError
from agent.integration.structured_response import (
    call_structured_json,
    repair_structured_fields,
    structured_failure_receipt,
)
from agent.llm_planner import LLMPlanner
from agent.models import AgentRunResult, RunStatus, TaskPlan
from agent.react.contracts import REACT_DECISION_SCHEMA_VERSION


class _RecoveryClient:
    def __init__(self, compact_payload):
        self.compact_payload = compact_payload
        self.calls: list[str] = []

    def complete_json(self, _messages, _schema, **_kwargs):
        self.calls.append("normal")
        raise PlanningError(
            "malformed provider response",
            category="planning",
            code="invalid_model_response",
            retryable=False,
        )

    def complete_compact_json(self, _messages, _schema, **_kwargs):
        self.calls.append("compact")
        return self.compact_payload


class M331StructuredResponseTests(unittest.TestCase):
    def test_structured_call_recovers_once_and_never_recurses(self):
        client = _RecoveryClient({"ok": True})

        result = call_structured_json(
            client,
            [],
            {"type": "object"},
            schema_name="test_contract",
        )

        self.assertEqual(result.payload, {"ok": True})
        self.assertEqual(result.recovery_attempts, 1)
        self.assertEqual(client.calls, ["normal", "compact"])

    def test_invalid_compact_response_stops_after_one_recovery(self):
        client = _RecoveryClient([])

        with self.assertRaises(PlanningError) as raised:
            call_structured_json(client, [], {"type": "object"})

        self.assertEqual(raised.exception.code, "invalid_model_response")
        self.assertEqual(client.calls, ["normal", "compact"])

    def test_field_repair_requires_one_unambiguous_alias(self):
        self.assertEqual(
            repair_structured_fields(
                {"content": "答案"},
                {"answer": ("content", "text")},
            ),
            {"answer": "答案"},
        )
        self.assertIsNone(
            repair_structured_fields(
                {"content": "答案", "text": "另一个答案"},
                {"answer": ("content", "text")},
            )
        )

    def test_planner_compact_recovery_preserves_task_plan_validation(self):
        client = _RecoveryClient(
            {
                "goal": "读取数据",
                "steps": [],
                "output": {"type": "metrics"},
            }
        )

        with self.assertRaises(PlanningError):
            LLMPlanner(client, ("safe_tool",)).plan("读取数据")

        self.assertEqual(client.calls, ["normal", "compact"])

    def test_answer_alias_is_repaired_but_extra_fields_are_rejected(self):
        result = AgentRunResult(
            run_id="m331-answer",
            status=RunStatus.COMPLETED,
            request="解释结果",
            plan=TaskPlan(
                "解释结果",
                [],
                {"type": "direct_answer", "message": "请解释结果"},
            ),
        )

        class AliasClient:
            def complete_json(self, _messages, _schema, **_kwargs):
                return {"content": "这是一个可读的回答。"}

        generated = LLMAnswerGenerator(AliasClient()).generate(result)
        self.assertEqual(generated.answer, "这是一个可读的回答。")

        class ExtraClient:
            def complete_json(self, _messages, _schema, **_kwargs):
                return {"answer": "回答", "debug": "不要传播"}

        with self.assertRaises(PlanningError) as raised:
            LLMAnswerGenerator(ExtraClient()).generate(result)
        self.assertEqual(raised.exception.code, "invalid_model_response")
        self.assertEqual(raised.exception.category, "answer")

    def test_failure_receipt_keeps_provider_timeout_classification(self):
        receipt = structured_failure_receipt(
            PlanningError(
                "timeout",
                category="provider",
                code="provider_timeout",
                retryable=True,
            ),
            stage="selection",
        )

        self.assertEqual(receipt["reason_code"], "provider_timeout")
        self.assertTrue(receipt["retryable"])
        self.assertEqual(receipt["recovery_attempts"], 0)

    def test_react_alias_repair_still_requires_react_contract(self):
        class ReactClient:
            def complete_json(self, _messages, _schema, **_kwargs):
                return {
                    "schema_version": REACT_DECISION_SCHEMA_VERSION,
                    "action": "call_tool",
                    "tool": "safe_tool",
                    "args": {"value": "demo"},
                }

        decision = LLMPlanner(ReactClient(), ("safe_tool",)).decide("读取数据")
        self.assertEqual(decision["tool_name"], "safe_tool")
        self.assertEqual(decision["arguments"], {"value": "demo"})


if __name__ == "__main__":
    unittest.main()
