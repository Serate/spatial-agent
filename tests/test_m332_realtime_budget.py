from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from agent.errors import RunTimedOut
from agent.runtime_core.run_budget import (
    RUN_BUDGET_SCHEMA_VERSION,
    RunBudget,
    RunBudgetError,
    project_run_budget,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class M332RunBudgetTests(unittest.TestCase):
    def test_phase_and_total_budget_bound_child_call(self):
        clock = _Clock()
        budget = RunBudget.from_values(
            total_seconds=4,
            planning_seconds=10,
            planning_attempt_seconds=3,
            clock=clock,
        )

        budget.start_phase("plan")
        self.assertEqual(budget.begin_attempt(), 1)
        self.assertEqual(budget.child_timeout(kind="planning"), 3)
        clock.advance(2)
        self.assertEqual(budget.child_timeout(10, kind="planning"), 2)
        clock.advance(2.1)

        with self.assertRaises(RunTimedOut) as raised:
            budget.check()
        self.assertEqual(raised.exception.code, "planner_timeout")
        self.assertEqual(raised.exception.phase, "plan")
        self.assertTrue(raised.exception.retryable)
        self.assertEqual(budget.receipt()["state"], "exhausted")

    def test_retry_and_heartbeat_counters_are_safe_receipt_data(self):
        clock = _Clock()
        budget = RunBudget.from_values(total_seconds=20, clock=clock, source="test")
        budget.start_phase("answer")
        budget.begin_attempt()
        budget.begin_attempt(retry=True)
        budget.record_heartbeat()
        clock.advance(1.25)

        receipt = budget.receipt()
        self.assertEqual(receipt["schema_version"], RUN_BUDGET_SCHEMA_VERSION)
        self.assertEqual(receipt["attempt"], 2)
        self.assertEqual(receipt["retry_count"], 1)
        self.assertEqual(receipt["heartbeat_count"], 1)
        self.assertEqual(receipt["phase"], "answer")
        self.assertEqual(receipt["phase_elapsed_ms"], 1250)
        self.assertNotIn("prompt", receipt)

    def test_projection_is_bounded_and_idempotent(self):
        value = {
            "schema_version": "wrong",
            "state": "not-a-state",
            "phase": "not-a-phase",
            "source": "x" * 200,
            "attempt": "bad",
            "run_remaining_ms": 999999999,
            "prompt": "private",
        }
        projected = project_run_budget(value)
        self.assertEqual(projected["schema_version"], RUN_BUDGET_SCHEMA_VERSION)
        self.assertEqual(projected["state"], "active")
        self.assertEqual(projected["phase"], "")
        self.assertEqual(projected["run_remaining_ms"], 86_400_000)
        self.assertNotIn("prompt", projected)
        self.assertEqual(project_run_budget(projected), projected)

    def test_invalid_phase_and_non_finite_limit_are_rejected(self):
        with self.assertRaises(RunBudgetError):
            RunBudget(phase_seconds={"unknown": 1})
        with self.assertRaises(RunBudgetError):
            RunBudget(total_seconds=float("inf"))

    @patch.dict(
        os.environ,
        {
            "SPATIAL_AGENT_ANSWER_TIMEOUT_SECONDS": "75",
            "SPATIAL_AGENT_PROVIDER_ATTEMPT_TIMEOUT_SECONDS": "45",
        },
        clear=False,
    )
    def test_environment_budget_controls_answer_and_provider_limits(self):
        budget = RunBudget.from_environment(total_seconds=180, source="test")

        self.assertEqual(budget.phase_seconds["answer"], 75)
        self.assertEqual(budget.provider_attempt_seconds, 45)
        budget.start_phase("answer")
        self.assertEqual(budget.child_timeout(kind="provider"), 45)


if __name__ == "__main__":
    unittest.main()
