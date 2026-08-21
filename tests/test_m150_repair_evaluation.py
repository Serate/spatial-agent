"""M150-A: offline capability-guided repair quality and entry consistency."""

import json
import unittest
from pathlib import Path

from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from evaluation.live_baseline import _result_evidence
from evaluation.model_evaluation import (
    CAPABILITY_REPAIR_EVIDENCE_SCHEMA_VERSION,
    REPAIR_EVIDENCE_SCHEMA_VERSION,
    compare_repair_evidence_entries,
    evaluate_capability_guided_repair,
    evaluate_model_replay_suite_file,
    summarize_capability_repair_quality,
)


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "m150_repair_evaluation.json"


class M150RepairEvaluationTests(unittest.TestCase):
    def test_offline_fixture_evaluates_expected_actual_and_classes(self):
        report = evaluate_model_replay_suite_file(FIXTURE)

        self.assertEqual(report["passed"], 3)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(
            report["capability_repair_evaluation"]["schema_version"],
            CAPABILITY_REPAIR_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(
            report["capability_repair_evaluation"]["repair_classes"],
            {"no_repair": 1, "rejected": 1, "repaired": 1},
        )

        repaired = report["results"][0]["capability_repair_quality"]
        self.assertEqual(
            repaired["expected"]["selected_capability_id"], "text_summary"
        )
        self.assertEqual(
            repaired["actual"]["selected_capability_id"], "text_summary"
        )
        self.assertEqual(repaired["actual"]["repair_class"], "repaired")
        self.assertTrue(repaired["passed"])

        rejected = report["results"][1]["capability_repair_quality"]
        self.assertEqual(rejected["actual"]["repair_class"], "rejected")
        self.assertTrue(rejected["passed"])

    def test_live_projection_uses_the_same_bounded_evidence_contract(self):
        plan = TaskPlan(
            goal="repair summary",
            steps=[PlanStep("summary", "summarize_text", {}, [])],
            output={"type": "text_summary_result"},
        )
        result = AgentRunResult(
            run_id="live-private-run",
            status=RunStatus.COMPLETED,
            request="private request",
            plan=plan,
            steps=[StepRun("summary", "summarize_text", {}, [], status="COMPLETED")],
            answer="已完成摘要。",
            plan_evidence={
                "selected_capability_id": "text_summary",
                "capability_candidate_ids": ["text_summary"],
            },
            replan_events=[
                {
                    "failed_step_id": "plan-validation",
                    "failed_tool": "planner",
                    "failure_category": "tool_validation",
                    "phase": "planning",
                    "replanned_step_ids": ["summary"],
                }
            ],
        )

        live = _result_evidence(
            result,
            {
                "id": "live-capability-repair",
                "kind": "untyped",
                "expected_status": "COMPLETED",
                "expected_capability": {
                    "selected": "text_summary",
                    "candidates": ["text_summary"],
                },
                "expected_repair_class": "repaired",
            },
            {},
            1,
        )
        quality = live["capability_repair_quality"]
        self.assertEqual(quality["schema_version"], CAPABILITY_REPAIR_EVIDENCE_SCHEMA_VERSION)
        self.assertTrue(quality["passed"])
        self.assertEqual(quality["actual"]["repair_class"], "repaired")
        self.assertEqual(live["repair_evidence"]["schema_version"], REPAIR_EVIDENCE_SCHEMA_VERSION)

        replay = evaluate_model_replay_suite_file(FIXTURE)["results"][0]
        comparison = compare_repair_evidence_entries(
            replay["repair_evidence"], live["repair_evidence"]
        )
        self.assertTrue(comparison["same_schema"])
        self.assertTrue(comparison["same_shape"])
        self.assertTrue(comparison["redacted"])
        self.assertTrue(comparison["passed"])

    def test_projection_drops_private_capability_and_provider_values(self):
        payload = {
            "status": "COMPLETED",
            "plan": {"steps": [], "output": {"type": "text_summary_result"}},
            "plan_evidence": {
                "selected_capability_id": "api_key",
                "capability_candidate_ids": [
                    "Bearer sk-secret-value",
                    "safe_capability",
                ],
            },
            "replan_events": [
                {
                    "failed_step_id": "repair",
                    "failed_tool": "planner",
                    "failure_category": "provider_error",
                    "error": "Authorization: Bearer sk-secret-value",
                }
            ],
        }
        quality = evaluate_capability_guided_repair(
            payload,
            expected={"expected_repair_class": "repaired"},
        )
        encoded = json.dumps(quality, ensure_ascii=False).lower()
        self.assertTrue(quality["passed"])
        self.assertNotIn("authorization", encoded)
        self.assertNotIn("sk-secret-value", encoded)
        self.assertNotIn("api_key", encoded)
        self.assertEqual(quality["actual"]["candidate_ids"], ["safe_capability"])

    def test_summary_accepts_live_case_shape_without_network(self):
        summary = summarize_capability_repair_quality(
            {
                "cases": [
                    {
                        "capability_repair_quality": {
                            "evaluated": True,
                            "passed": True,
                            "actual": {"repair_class": "rejected"},
                        }
                    }
                ]
            }
        )
        self.assertEqual(summary["evaluated_count"], 1)
        self.assertEqual(summary["repair_classes"], {"rejected": 1})
        self.assertTrue(summary["passed"])


if __name__ == "__main__":
    unittest.main()
