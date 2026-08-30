"""Compact M332-C checks for provider deadline propagation and answer streaming."""

from __future__ import annotations

import unittest

from agent.answer_generation import LLMAnswerGenerator
from agent.errors import PlanningError, RunTimedOut
from agent.integration.structured_response import call_structured_json
from agent.llm_planner import LLMPlanner
from agent.models import AgentRunResult, RunStatus
from agent.runtime_core.run_budget import RunBudget


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class _PlanClient:
    def __init__(self, clock: _Clock | None = None) -> None:
        self.calls: list[dict] = []
        self.clock = clock

    def complete_json(self, _messages, _schema, **kwargs):
        self.calls.append(kwargs)
        if self.clock is not None:
            self.clock.value = 2.0
            raise PlanningError(
                "provider timed out",
                category="provider",
                code="provider_timeout",
                retryable=True,
            )
        return {
            "outcome": "direct_answer",
            "goal": "回答问题",
            "steps": [],
            "message": "这是一个直接回答",
            "output": {"type": "direct_answer"},
        }


class _RecoveryClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete_json(self, _messages, _schema, **kwargs):
        self.calls.append(kwargs)
        raise PlanningError(
            "invalid response",
            category="planning",
            code="invalid_model_response",
            retryable=False,
        )

    def complete_compact_json(self, _messages, _schema, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


class _StreamClient:
    def __init__(self) -> None:
        self.kwargs = None

    def stream_text(self, _messages, **kwargs):
        self.kwargs = kwargs
        if callable(kwargs.get("on_progress")):
            kwargs["on_progress"]({"kind": "provider_stream_delta", "received_chars": 2})
        yield "你好"
        yield "，结果已就绪。"


class _ShapeErrorStreamClient:
    def __init__(self) -> None:
        self.complete_calls = 0

    def stream_text(self, _messages, **_kwargs):
        raise PlanningError(
            "stream did not contain visible answer text",
            category="planning",
            code="invalid_model_response",
            retryable=False,
        )

    def complete_json(self, _messages, _schema, **_kwargs):
        self.complete_calls += 1
        return {"answer": "已使用结构化结果完成回答。"}


class M332ProviderBudgetTests(unittest.TestCase):
    def test_planner_receives_bounded_deadline_and_timeout(self):
        client = _PlanClient()
        budget = RunBudget.from_values(
            total_seconds=10,
            planning_seconds=8,
            planning_attempt_seconds=3,
            clock=_Clock(),
        )

        plan = LLMPlanner(client, ()).plan("读取数据", budget=budget)

        self.assertEqual(plan.output["type"], "direct_answer")
        self.assertEqual(client.calls[0]["timeout_seconds"], 3)
        self.assertEqual(client.calls[0]["deadline"], 3)
        self.assertEqual(budget.attempt, 1)

    def test_structured_recovery_gets_a_fresh_timeout(self):
        client = _RecoveryClient()
        timeouts = iter((4.0, 1.5))
        result = call_structured_json(
            client,
            [],
            {"type": "object"},
            timeout_provider=lambda: next(timeouts),
        )

        self.assertEqual(result.payload, {"ok": True})
        self.assertEqual(
            [call["timeout_seconds"] for call in client.calls],
            [4.0, 1.5],
        )

    def test_answer_stream_receives_budget_and_only_safe_progress(self):
        client = _StreamClient()
        deltas = []
        progress = []
        budget = RunBudget.from_values(
            total_seconds=20,
            answer_seconds=6,
            provider_attempt_seconds=2,
        )
        result = AgentRunResult(
            run_id="m332-answer",
            status=RunStatus.COMPLETED,
            request="解释结果",
        )

        generated = LLMAnswerGenerator(client).generate_stream(
            result,
            on_delta=deltas.append,
            budget=budget,
            on_progress=progress.append,
        )

        self.assertEqual(generated.answer, "你好，结果已就绪。")
        self.assertEqual(deltas, ["你好", "，结果已就绪。"])
        self.assertEqual(client.kwargs["timeout_seconds"], 2)
        self.assertTrue(progress)
        self.assertTrue(all("prompt" not in item for item in progress))

    def test_planner_provider_error_becomes_phase_timeout_when_budget_is_exhausted(self):
        clock = _Clock()
        budget = RunBudget.from_values(
            total_seconds=10,
            planning_seconds=1,
            planning_attempt_seconds=1,
            clock=clock,
        )

        with self.assertRaises(RunTimedOut) as raised:
            LLMPlanner(_PlanClient(clock), ()).plan("读取数据", budget=budget)

        self.assertEqual(raised.exception.code, "planner_timeout")

    def test_answer_stream_falls_back_after_empty_visible_stream(self):
        client = _ShapeErrorStreamClient()
        deltas = []
        budget = RunBudget.from_values(
            total_seconds=20,
            answer_seconds=6,
            provider_attempt_seconds=2,
        )
        result = AgentRunResult(
            run_id="m332-answer-fallback",
            status=RunStatus.COMPLETED,
            request="解释结果",
        )

        generated = LLMAnswerGenerator(client).generate_stream(
            result,
            on_delta=deltas.append,
            budget=budget,
        )

        self.assertEqual(generated.answer, "已使用结构化结果完成回答。")
        self.assertEqual(deltas, ["已使用结构化结果完成回答。"])
        self.assertEqual(client.complete_calls, 1)
        self.assertFalse(generated.evidence["streaming"])


if __name__ == "__main__":
    unittest.main()
