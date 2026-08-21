"""M155: plan-quality evidence is stable across result and async boundaries."""

import unittest

from agent.plan_quality import (
    PLAN_QUALITY_EVIDENCE_SCHEMA_VERSION,
    diagnose_plan,
    project_plan_quality_evidence,
)
from agent.service_async import (
    build_async_result_evidence,
    normalize_async_result_evidence,
)
from agent.models import PlanStep, TaskPlan
from agent.workflow_templates import workflow_template_context_summary
from evaluation.contract_harness import normalize_result
from result_contract import build_replanning_evidence, build_result_contract


def _overview_plan():
    template = next(
        item
        for item in workflow_template_context_summary(compact=True)["templates"]
        if item["id"] == "spatial_overview"
    )
    return TaskPlan(
        "overview",
        [
            PlanStep(
                item["id"],
                item["tool"],
                {key: None for key in item.get("arg_keys", [])},
                list(item.get("depends_on") or []),
            )
            for item in template["step_blueprint"]
        ],
        {"type": "spatial_overview_result"},
    )


class M155PlanQualityContractTests(unittest.TestCase):
    def test_unique_blueprint_is_projected_as_passed(self):
        diagnostic = diagnose_plan(
            _overview_plan(),
            {"workflow_templates": workflow_template_context_summary(compact=True)},
        )
        projected = project_plan_quality_evidence(diagnostic)
        self.assertEqual(projected["schema_version"], PLAN_QUALITY_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(projected["state"], "passed")
        self.assertEqual(projected["template_id"], "spatial_overview")

    def test_non_unique_blueprint_is_explicitly_unavailable(self):
        context = {
            "workflow_templates": {
                "templates": [
                    {"id": "one", "result_types": ["open_result"], "step_blueprint": []},
                    {"id": "two", "result_types": ["open_result"], "step_blueprint": []},
                ]
            }
        }
        candidate = TaskPlan(
            "open",
            [PlanStep("answer", "summarize_text", {}, [])],
            {"type": "open_result"},
        )
        projected = project_plan_quality_evidence(diagnose_plan(candidate, context))
        self.assertEqual(projected["state"], "unavailable")
        self.assertTrue(projected["passed"])
        self.assertEqual(projected["reason_code"], "workflow_blueprint_unavailable")
        self.assertEqual(projected["candidate_template_ids"], ["one", "two"])

    def test_result_and_async_projection_retain_the_same_plan_quality(self):
        plan = _overview_plan()
        plan_dict = {
            "goal": plan.goal,
            "steps": [
                {
                    "id": step.id,
                    "tool": step.tool,
                    "args": step.args,
                    "depends_on": step.depends_on,
                }
                for step in plan.steps
            ],
            "output": plan.output,
        }
        diagnostic = diagnose_plan(
            plan,
            {"workflow_templates": workflow_template_context_summary(compact=True)},
        )
        evidence = project_plan_quality_evidence(diagnostic)
        payload = {
            "run_id": "m155-run",
            "status": "COMPLETED",
            "answer": "已完成空间概况。",
            "result_type": "spatial_overview_result",
            "plan": plan_dict,
            "plan_evidence": {"available": True, "plan_quality": evidence},
            "steps": [],
        }
        contract = build_result_contract(payload)
        async_evidence = normalize_async_result_evidence(
            build_async_result_evidence(contract, status="COMPLETED"),
            status="COMPLETED",
        )
        self.assertEqual(
            contract["planning"]["plan_quality"],
            evidence,
        )
        self.assertEqual(
            async_evidence["planning"]["plan_quality"],
            evidence,
        )
        normalized = normalize_result({**payload, "result": contract})
        self.assertEqual(
            normalized.as_dict()["plan_quality"],
            evidence,
        )

    def test_replanning_events_keep_before_and_after_quality(self):
        events = build_replanning_evidence(
            [{
                "failed_step_id": "plan-validation",
                "failed_tool": "planner",
                "failure_category": "tool_validation",
                "phase": "planning",
                "replanned_step_ids": ["answer"],
                "plan_quality_before": {
                    "available": True,
                    "passed": False,
                    "reason_code": "workflow_blueprint_mismatch",
                    "template_id": "open",
                    "issues": [{"code": "template_step_count", "expected": 2, "actual": 3}],
                },
                "plan_quality_after": {
                    "available": True,
                    "passed": True,
                    "reason_code": "ok",
                    "template_id": "open",
                },
            }]
        )
        event = events["events"][0]
        self.assertEqual(event["plan_quality_before"]["state"], "mismatch")
        self.assertEqual(event["plan_quality_after"]["state"], "passed")


if __name__ == "__main__":
    unittest.main()
