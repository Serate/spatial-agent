import importlib.util
import unittest
from pathlib import Path

from agent.answer_composer import AnswerComposer
from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from run_demo import build_runtime


HAS_GIS = importlib.util.find_spec("geopandas") is not None
HAS_LOCAL_DATA = Path("D:/dataset/agent/\u6e56\u5317\u7701_\u53bf.geojson").exists()
ADMIN_QUERY = "\u67e5\u8be2\u6d2a\u5c71\u533a\u884c\u653f\u533a\u8fb9\u754c"
ROAD_SLOPE_QUERY = "\u67e5\u8be2\u8ddd\u79bb\u4e3b\u5e72\u9053500\u7c73\u4ee5\u5185\u3001\u5761\u5ea6\u8d85\u8fc725\u5ea6\u7684\u533a\u57df\u3002"


class M8AnswerComposerTests(unittest.TestCase):
    def test_default_answer_keeps_result_ref_and_count(self):
        result = build_runtime("rule").run(ROAD_SLOPE_QUERY)
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertIn("memory://join/roads-slope", result.answer)
        self.assertIn("\u5df2\u5b8c\u6210", result.answer)
        self.assertIn("\u547d\u4e2d\u6570\u91cf", result.answer)

    def test_admin_answer_is_user_facing(self):
        result = build_runtime("rule").run(ADMIN_QUERY)
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertIn("\u5df2\u627e\u5230", result.answer)
        self.assertIn("1", result.answer)
        self.assertIn("memory://range/admin_areas", result.answer)

    def test_raster_answer_uses_tool_result_when_output_type_is_imprecise(self):
        result = AgentRunResult(
            run_id="run-1",
            status=RunStatus.COMPLETED,
            request="query raster metadata",
            plan=TaskPlan(
                goal="Query DEM raster metadata",
                steps=[PlanStep("raster", "get_raster_metadata", {"dataset": "dem"})],
                output={"type": "metadata"},
            ),
            steps=[
                StepRun(
                    id="raster",
                    tool="get_raster_metadata",
                    args={"dataset": "dem"},
                    status="COMPLETED",
                    result={
                        "dataset": "dem",
                        "file_count": 9,
                        "metadata": {"width": 100, "height": 80, "band_count": 1},
                        "metrics": {"probed_files": 2},
                    },
                )
            ],
        )

        answer = AnswerComposer().compose(result)

        self.assertIn("dem \u6805\u683c\u5143\u6570\u636e", answer)
        self.assertIn("\u6587\u4ef6\u6570\uff1a9", answer)
        self.assertIn("\u9996\u4e2a\u6837\u672c\u5c3a\u5bf8\uff1a100x80", answer)

    def test_specialized_results_are_summarized_without_output_type_hint(self):
        cases = [
            (
                "get_zonal_land_use_distribution",
                {
                    "admin_name": "洪山区",
                    "statistics": {
                        "category_count": 2,
                        "valid_pixel_count": 100,
                        "categories": [{"value": 80, "share": 0.6}],
                    },
                },
                "土地利用分布",
            ),
            (
                "get_zonal_buildability_analysis",
                {
                    "admin_name": "洪山区",
                    "statistics": {
                        "candidate_pixel_count": 20,
                        "valid_pixel_count": 100,
                        "candidate_ratio": 0.2,
                        "slope_limit_degrees": 15,
                    },
                },
                "建设候选演示筛选",
            ),
        ]
        for tool, tool_result, expected in cases:
            with self.subTest(tool=tool):
                run = AgentRunResult(
                    run_id="specialized-" + tool,
                    status=RunStatus.COMPLETED,
                    request="空间分析",
                    plan=TaskPlan(
                        goal="specialized result",
                        steps=[PlanStep("step", tool, {})],
                        output={"type": "unknown"},
                    ),
                    steps=[StepRun("step", tool, {}, status="COMPLETED", result=tool_result)],
                )
                self.assertIn(expected, AnswerComposer().compose(run))


@unittest.skipUnless(HAS_GIS and HAS_LOCAL_DATA, "requires geopandas and local admin GeoJSON")
class M8AnswerComposerLocalBackendTests(unittest.TestCase):
    def test_admin_answer_mentions_real_dataset_context(self):
        result = build_runtime("rule", "local").run(ADMIN_QUERY)
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertIn("\u6d2a\u5c71\u533a", result.answer)
        self.assertIn("EPSG:4490", result.answer)
        self.assertIn("geojson://range/admin_areas", result.answer)


if __name__ == "__main__":
    unittest.main()
