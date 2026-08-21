"""M179: replay/live evaluation consumes the shared evidence projection."""

import json
from pathlib import Path
import unittest

from agent.evidence_projection import EVIDENCE_PROJECTION_SCHEMA_VERSION
from agent.models import AgentRunResult, PlanStep, RunStatus, TaskPlan
from evaluation.live_baseline import _result_evidence
from evaluation.model_evaluation import (
    evaluate_model_replay_suite_file,
    project_repair_evidence,
    summarize_evidence_projection,
)


ROOT = Path(__file__).parents[1]


def _result():
    return AgentRunResult(
        run_id="m179-evaluation-run",
        status=RunStatus.COMPLETED,
        request="请生成一个摘要",
        plan=TaskPlan(
            goal="生成摘要",
            steps=[PlanStep("summary", "summarize_text", {"text": "安全文本"}, [])],
            output={"type": "text_summary_result"},
        ),
        plan_evidence={
            "available": True,
            "workflow_selection": {
                "schema_version": "spatial-agent.workflow-selection.v1",
                "state": "selected",
                "reason_code": "workflow_selected",
                "source": "domain_discovery",
                "selected_capability_id": "text_summary",
                "candidate_ids": ["text_summary"],
            },
            "planner_selection": {
                "schema_version": "spatial-agent.planner-selection.v1",
                "state": "matched",
                "reason_code": "planner_matches_selected_capability",
                "result_type": "text_summary_result",
                "selected_capability_id": "text_summary",
                "planner_capability_id": "text_summary",
                "planner_kind": "RuleBasedPlanner",
                "candidate_ids": ["text_summary"],
            },
        },
        answer="已完成摘要。",
    )


class M179EvidenceEvaluationTests(unittest.TestCase):
    def test_runtime_repair_evidence_uses_shared_projection_and_migration(self):
        evidence = project_repair_evidence(_result())

        projection = evidence["evidence_projection"]
        self.assertEqual(
            projection["schema_version"], EVIDENCE_PROJECTION_SCHEMA_VERSION
        )
        self.assertEqual(projection["migration"]["state"], "current")
        self.assertEqual(
            evidence["evidence_migration"], projection["migration"]
        )
        self.assertEqual(
            evidence["evidence_registry_completeness"],
            projection["evidence_registry_completeness"],
        )

    def test_live_result_and_repair_projection_share_evidence_shape(self):
        result = _result()
        direct = project_repair_evidence(result)
        live = _result_evidence(
            result,
            {"id": "m179-live", "kind": "untyped", "expected_status": "COMPLETED"},
            {},
            1,
        )["repair_evidence"]

        self.assertEqual(live["evidence_projection"], direct["evidence_projection"])
        self.assertEqual(live["evidence_migration"], direct["evidence_migration"])

    def test_replay_report_exposes_projection_summary(self):
        report = evaluate_model_replay_suite_file(
            ROOT / "tests" / "fixtures" / "m69_model_replay_suite.json"
        )

        summary = report["evidence_projection"]
        self.assertEqual(summary["schema_version"], EVIDENCE_PROJECTION_SCHEMA_VERSION)
        self.assertGreater(summary["projection_count"], 0)
        self.assertIn("current", summary["migration_states"])
        self.assertTrue(summary["passed"])

    def test_summary_rejects_legacy_or_unknown_evidence_states(self):
        summary = summarize_evidence_projection(
            [
                {
                    "repair_evidence": {
                        "evidence_projection": {
                            "schema_version": EVIDENCE_PROJECTION_SCHEMA_VERSION,
                            "migration": {
                                "state": "legacy_incomplete",
                            },
                            "evidence_registry_completeness": {"passed": False},
                        }
                    }
                },
                {
                    "repair_evidence": {
                        "evidence_projection": {
                            "schema_version": EVIDENCE_PROJECTION_SCHEMA_VERSION,
                            "migration": {
                                "state": "unknown_schema",
                            },
                            "evidence_registry_completeness": {"passed": False},
                        }
                    }
                },
            ]
        )

        self.assertEqual(summary["migration_states"]["legacy_incomplete"], 1)
        self.assertEqual(summary["migration_states"]["unknown_schema"], 1)
        self.assertFalse(summary["passed"])
        self.assertNotIn("m179-evaluation-run", json.dumps(summary))

    def test_unavailable_turns_are_reported_but_do_not_fail_current_results(self):
        summary = summarize_evidence_projection(
            [
                {
                    "repair_evidence": {
                        "evidence_projection": {
                            "schema_version": EVIDENCE_PROJECTION_SCHEMA_VERSION,
                            "migration": {"state": "unavailable"},
                            "evidence_registry_completeness": {"passed": False},
                        }
                    }
                },
                {
                    "repair_evidence": {
                        "evidence_projection": {
                            "schema_version": EVIDENCE_PROJECTION_SCHEMA_VERSION,
                            "migration": {"state": "current"},
                            "evidence_registry_completeness": {"passed": True},
                        }
                    }
                },
            ]
        )

        self.assertEqual(summary["migration_states"]["unavailable"], 1)
        self.assertEqual(summary["migration_states"]["current"], 1)
        self.assertTrue(summary["passed"])


if __name__ == "__main__":
    unittest.main()
