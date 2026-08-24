import unittest
from pathlib import Path

from tests.console_source import read_console_source
from unittest.mock import patch

from agent.answer_composer import AnswerComposer
from agent.models import AgentRunResult, RunStatus, StepRun, TaskPlan
from agent.service import AgentService


ROOT = Path(__file__).parents[1]


ANALYSIS_READY = {
    "status": "ready",
    "required": True,
    "derived_version": "analysis-ready-v1",
    "target_grid": {"crs": "EPSG:32649", "resolution": [30.0, 30.0]},
    "grid_alignment": {"status": "aligned"},
    "verification_mode": "metadata",
    "data_readiness": "ready",
}


class M71EvidenceConsistencyTests(unittest.TestCase):
    def test_threshold_and_region_comparisons_preserve_analysis_ready_evidence(self):
        service = AgentService()
        with patch("agent.service._analysis_ready_summary", return_value=ANALYSIS_READY):
            threshold = service.compare_buildability("洪山区", [15, 20], backend="memory")
            regions = service.compare_buildability_regions(
                ["洪山区", "江夏区"], threshold=20, backend="memory"
            )

        self.assertEqual(threshold["analysis_ready"]["derived_version"], "analysis-ready-v1")
        self.assertEqual(len(threshold["results"]), 2)
        self.assertTrue(all(row["analysis_ready"]["grid_alignment"]["status"] == "aligned" for row in threshold["results"]))
        self.assertEqual(regions["analysis_ready"]["target_grid"]["crs"], "EPSG:32649")
        self.assertTrue(all("analysis_ready" in row for row in regions["results"]))

    def test_constrained_answer_mentions_analysis_ready_version(self):
        health = {"status": "ready", "analysis_ready": ANALYSIS_READY}
        result = AgentRunResult(
            run_id="m71-constrained",
            status=RunStatus.COMPLETED,
            request="道路与水体约束建设筛选",
            plan=TaskPlan(
                goal="screen",
                steps=[],
                output={"type": "constrained_buildability_result"},
            ),
            steps=[
                StepRun(
                    id="health",
                    tool="get_dataset_health_report",
                    args={},
                    status="COMPLETED",
                    result=health,
                ),
                StepRun(
                    id="constrained",
                    tool="get_zonal_constrained_buildability_analysis",
                    args={},
                    status="COMPLETED",
                    result={
                        "admin_name": "洪山区",
                        "statistics": {"candidate_ratio": 0.1},
                        "constraint_summary": {
                            "candidate_features": 2,
                            "eligible_features": 1,
                            "water_excluded_features": 1,
                            "road_distance_m": 500,
                        },
                    },
                ),
            ],
        )
        answer = AnswerComposer().compose(result)
        self.assertIn("analysis-ready-v1", answer)
        self.assertIn("EPSG:32649", answer)

    def test_console_surfaces_comparison_evidence(self):
        html = read_console_source(ROOT)
        for marker in (
            "function comparisonEvidenceText(data)",
            "data.analysis_ready",
            "对齐 ",
            "分析就绪 ",
        ):
            self.assertIn(marker, html)


if __name__ == "__main__":
    unittest.main()
