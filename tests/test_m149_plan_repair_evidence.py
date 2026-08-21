"""M149-A: unified, bounded repair evidence for replay and live results."""

import json
import unittest
from pathlib import Path

from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from evaluation.live_baseline import _result_evidence
from evaluation.model_evaluation import (
    REPAIR_EVIDENCE_SCHEMA_VERSION,
    evaluate_model_replay_suite_file,
    project_repair_evidence,
)


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "m149_plan_repair_evidence.json"


class M149PlanRepairEvidenceTests(unittest.TestCase):
    def test_offline_replay_projects_plan_repair_without_counting_clarification(self):
        report = evaluate_model_replay_suite_file(FIXTURE)

        self.assertTrue(report["passed"] == 1)
        self.assertEqual(report["failed"], 0)
        evidence = report["results"][0]["repair_evidence"]
        self.assertEqual(evidence["schema_version"], REPAIR_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(evidence["repair_count"], 1)
        self.assertEqual(evidence["clarification_count"], 0)
        self.assertTrue(evidence["expected_match"])
        self.assertTrue(report["repair_evidence"]["available"])

    def test_runtime_projection_is_bounded_and_redacted(self):
        payload = {
            "status": "COMPLETED",
            "result_type": "text_summary_result",
            "plan": {"steps": [{"id": "final", "tool": "summarize_text"}], "output": {"type": "text_summary_result"}},
            "replan_events": [{
                "failed_step_id": "plan-validation",
                "failed_tool": "planner",
                "failure_category": "tool_validation",
                "phase": "planning",
                "replanned_step_ids": [f"step-{index}" for index in range(40)],
                "latency_ms": 12.3456,
                "occurred_at": 999999,
                "error": "Authorization: Bearer sk-do-not-copy",
            }] * 12,
        }

        evidence = project_repair_evidence(payload)
        self.assertEqual(evidence["repair_count"], 8)
        self.assertLessEqual(len(evidence["lineage"]["events"]), 8)
        self.assertLessEqual(len(evidence["lineage"]["events"][0]["replanned_step_ids"]), 24)
        encoded = json.dumps(evidence, ensure_ascii=False).lower()
        self.assertNotIn("occurred_at", encoded)
        self.assertNotIn("authorization", encoded)
        self.assertNotIn("sk-do-not-copy", encoded)
        self.assertNotIn("error", encoded)

    def test_live_result_uses_the_same_repair_projection_shape(self):
        plan = TaskPlan(
            goal="repair summary",
            steps=[PlanStep("summary", "summarize_text", {}, [])],
            output={"type": "text_summary_result"},
        )
        result = AgentRunResult(
            run_id="live-run-private-id",
            status=RunStatus.COMPLETED,
            request="private request must not enter repair evidence",
            plan=plan,
            steps=[StepRun("summary", "summarize_text", {}, [], status="COMPLETED")],
            answer="已完成摘要。",
            replan_events=[{
                "failed_step_id": "plan-validation",
                "failed_tool": "planner",
                "failure_category": "planner_error",
                "phase": "planning",
                "replanned_step_ids": ["summary"],
            }],
        )

        evidence = _result_evidence(
            result,
            {"id": "live-repair", "kind": "untyped", "expected_status": "COMPLETED"},
            {},
            1,
        )["repair_evidence"]
        self.assertEqual(evidence["schema_version"], REPAIR_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(evidence["lineage"]["events"][0]["phase"], "planning")
        encoded = json.dumps(evidence, ensure_ascii=False)
        self.assertNotIn("live-run-private-id", encoded)
        self.assertNotIn("private request", encoded)


if __name__ == "__main__":
    unittest.main()
