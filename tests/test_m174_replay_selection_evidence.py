"""M174: replay and live reports expose the same bounded planner selection."""

from pathlib import Path
import unittest

from agent.models import AgentRunResult, PlanStep, RunStatus, TaskPlan
from agent.service import AgentService
from evaluation.live_baseline import _result_evidence
from evaluation.model_evaluation import (
    PLANNER_SELECTION_EVIDENCE_SCHEMA_VERSION,
    evaluate_model_replay_suite_file,
    project_repair_evidence,
    summarize_selection_evidence,
)
from tests.test_m166_multi_candidate_selection import AmbiguousTextDomainPack


ROOT = Path(__file__).parents[1]


class M174ReplaySelectionEvidenceTests(unittest.TestCase):
    def test_replay_report_contains_planner_selection_for_each_turn(self):
        report = evaluate_model_replay_suite_file(
            ROOT / "tests" / "fixtures" / "m69_model_replay_suite.json"
        )
        for fixture in report["results"]:
            for turn in fixture["turns"]:
                selection = turn["repair_evidence"]["planner_selection"]
                self.assertEqual(
                    selection["schema_version"],
                    PLANNER_SELECTION_EVIDENCE_SCHEMA_VERSION,
                )
                self.assertIn(
                    selection["state"],
                    {"matched", "mismatch", "unresolved", "unavailable", "not_applicable"},
                )

    def test_live_and_replay_selection_projections_have_one_shape(self):
        plan = TaskPlan(
            goal="summary",
            steps=[PlanStep("summary", "summarize_text", {"text": "安全摘要"}, [])],
            output={"type": "text_summary_result"},
        )
        result = AgentRunResult(
            run_id="m174-live",
            status=RunStatus.COMPLETED,
            request="请摘要文本",
            plan=plan,
            plan_evidence={
                "planner_selection": {
                    "schema_version": "spatial-agent.planner-selection.v1",
                    "state": "matched",
                    "reason_code": "planner_matches_selected_capability",
                    "result_type": "text_summary_result",
                    "selected_capability_id": "text_summary",
                    "planner_capability_id": "text_summary",
                    "planner_kind": "LLMPlanner",
                    "candidate_ids": ["text_summary"],
                }
            },
        )
        live = project_repair_evidence(result)
        self.assertEqual(
            live["planner_selection"]["schema_version"],
            PLANNER_SELECTION_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(live["planner_selection"]["state"], "matched")

        baseline = _result_evidence(
            result,
            {
                "id": "m174-live-case",
                "kind": "untyped",
                "expected_status": "COMPLETED",
            },
            {},
            1,
        )
        self.assertEqual(
            baseline["repair_evidence"]["planner_selection"],
            live["planner_selection"],
        )

    def test_selection_summary_counts_replay_and_ambiguous_states(self):
        report = evaluate_model_replay_suite_file(
            ROOT / "tests" / "fixtures" / "m69_model_replay_suite.json"
        )
        summary = summarize_selection_evidence(report)
        self.assertGreater(summary["planner_selection_count"], 0)
        self.assertIn("matched", summary["planner_states"])

        service = AgentService(domain_pack=AmbiguousTextDomainPack())
        try:
            pending = service.run(
                "请处理这段内容",
                session_id="m174-ambiguous",
                planner="rule",
                backend="memory",
            )
        finally:
            service.close()
        ambiguous = project_repair_evidence(pending)
        self.assertEqual(ambiguous["workflow_selection"]["state"], "ambiguous")


if __name__ == "__main__":
    unittest.main()
