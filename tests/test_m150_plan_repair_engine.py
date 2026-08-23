"""M150-D: public contract tests for the bounded planning-repair seam."""

import unittest

from agent.models import PlanStep, TaskPlan
from agent.plan_repair import (
    PlanRepairEngine,
    PlanRepairInput,
    PlanRepairOutcome,
)
from agent.replanning import ReplanningPolicy


def _candidate_plan() -> TaskPlan:
    return TaskPlan(
        goal="repair a plan",
        steps=[PlanStep("invalid", "safe_tool", {})],
        output={"type": "demo_result"},
    )


def _replacement_plan() -> TaskPlan:
    return TaskPlan(
        goal="repaired plan",
        steps=[PlanStep("repaired", "safe_tool", {})],
        output={"type": "demo_result"},
    )


def _repair_input(**kwargs) -> PlanRepairInput:
    values = {
        "request": "repair this plan",
        "candidate": _candidate_plan(),
        "workflow": None,
        "validation_error": "planner selected an invalid tool",
    }
    values.update(kwargs)
    return PlanRepairInput(**values)


class _RecordingPlanner:
    def __init__(self, replacement=None):
        self.replacement = replacement or _replacement_plan()
        self.calls = 0
        self.contexts = []

    def plan(self, request, workflow=None, context=None):
        del request, workflow
        self.calls += 1
        self.contexts.append(context)
        return self.replacement


def _engine(planner, *, policy=None, validator=None, control_calls=None):
    if control_calls is None:
        control_calls = []

    def control_check(run_id, deadline):
        control_calls.append((run_id, deadline))

    return PlanRepairEngine(
        planner,
        policy or ReplanningPolicy(limit=1),
        available_tools=lambda: ["safe_tool", "another_tool"],
        validate_plan=validator or (lambda plan, workflow: None),
        control_check=control_check,
    )


class M150PlanRepairEngineTests(unittest.TestCase):
    def test_llm_repair_receives_only_bounded_capability_context(self):
        planner = _RecordingPlanner()
        engine = _engine(planner)
        capability_context = {
            "available_tools": ["tool-{}".format(index) for index in range(80)],
            "capability_catalog": {"description": "x" * 500},
            "unexpected_private_section": "must not reach planner",
        }

        outcome = engine.repair(
            _repair_input(capability_context=capability_context)
        )

        self.assertIsInstance(outcome, PlanRepairOutcome)
        self.assertEqual(outcome.status, "repaired")
        self.assertEqual(outcome.reason_code, "ok")
        context = planner.contexts[0]
        bounded = context["capability_context"]
        self.assertEqual(len(bounded["available_tools"]), 64)
        self.assertEqual(len(bounded["capability_catalog"]["description"]), 320)
        self.assertNotIn("unexpected_private_section", bounded)

    def test_replacement_is_accepted_only_after_validator_passes(self):
        planner = _RecordingPlanner()
        validator_calls = []

        def reject_replacement(plan, workflow):
            validator_calls.append((plan, workflow))
            raise ValueError("replacement violates the plan contract")

        outcome = _engine(planner, validator=reject_replacement).repair(
            _repair_input()
        )

        self.assertEqual(planner.calls, 1)
        self.assertEqual(len(validator_calls), 1)
        self.assertIs(validator_calls[0][0], planner.replacement)
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason_code, "replacement_invalid")
        self.assertIsNone(outcome.plan)
        self.assertIsInstance(outcome.event, dict)
        self.assertEqual(outcome.event.get("phase"), "planning")
        self.assertEqual(outcome.event.get("repair_status"), "failed")
        self.assertEqual(
            outcome.event.get("repair_reason_code"), "replacement_invalid"
        )

    def test_rule_planner_does_not_trigger_repair(self):
        planner = _RecordingPlanner()
        planner.capability_rules = ("deterministic-rule",)
        control_calls = []

        outcome = _engine(planner, control_calls=control_calls).repair(
            _repair_input()
        )

        self.assertEqual(planner.calls, 0)
        self.assertEqual(control_calls, [])
        self.assertEqual(outcome.status, "not_applicable")
        self.assertEqual(outcome.reason_code, "rule_planner")
        self.assertFalse(outcome.repaired)

    def test_repair_budget_exhaustion_skips_planner(self):
        planner = _RecordingPlanner()
        control_calls = []

        outcome = _engine(
            planner,
            policy=ReplanningPolicy(limit=0),
            control_calls=control_calls,
        ).repair(_repair_input())

        self.assertEqual(planner.calls, 0)
        self.assertEqual(control_calls, [])
        self.assertEqual(outcome.status, "rejected")
        self.assertEqual(outcome.reason_code, "repair_budget_exhausted")

    def test_planner_failure_returns_a_safe_reason_code(self):
        class FailingPlanner(_RecordingPlanner):
            def plan(self, request, workflow=None, context=None):
                del request, workflow, context
                self.calls += 1
                raise RuntimeError("provider key=secret-token and raw response")

        planner = FailingPlanner()
        outcome = _engine(planner).repair(_repair_input())

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason_code, "replacement_invalid")
        self.assertNotIn("secret-token", outcome.reason_code)
        self.assertNotIn("raw response", outcome.reason_code)
        self.assertIsNone(outcome.plan)
        self.assertIsInstance(outcome.event, dict)
        self.assertEqual(outcome.event.get("repair_status"), "failed")
        self.assertEqual(
            outcome.event.get("repair_reason_code"), "replacement_invalid"
        )
        self.assertNotIn("secret-token", str(outcome.event))
        self.assertNotIn("raw response", str(outcome.event))


if __name__ == "__main__":
    unittest.main()
