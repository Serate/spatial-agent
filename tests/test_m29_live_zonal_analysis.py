import os
import unittest

from result_contract import build_result_contract
from run_demo import build_runtime


@unittest.skipUnless(
    os.environ.get("SPATIAL_AGENT_LIVE_OPENAI") == "1"
    and os.environ.get("SPATIAL_AGENT_LIVE_GIS") == "1",
    "set SPATIAL_AGENT_LIVE_OPENAI=1 and SPATIAL_AGENT_LIVE_GIS=1 to run live GIS planner smoke",
)
class M29LiveZonalAnalysisTests(unittest.TestCase):
    def test_live_model_plans_and_executes_zonal_dem_analysis(self):
        result = build_runtime("openai", "local").run("分析洪山区DEM高程概况")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertTrue(result.steps)
        step = next(step for step in result.steps if step.tool == "get_zonal_raster_statistics")
        self.assertEqual(step.status, "COMPLETED")
        statistics = step.result["statistics"]
        self.assertIsNone(statistics.get("error"))
        self.assertGreater(statistics["valid_pixel_count"], 0)
        self.assertIn("洪山区", result.answer)
        contract = build_result_contract({**result.to_dict(), "result_type": result.plan.output["type"]})
        self.assertEqual(contract["type"], result.plan.output["type"])
        self.assertTrue(contract["references"])
        self.assertTrue(contract["data"]["evidence_steps"])

    def test_live_model_plans_composite_admin_raster_analysis(self):
        result = build_runtime("openai", "local").run(
            "查询洪山区行政区边界并分析DEM高程概况"
        )

        self.assertEqual(result.status.value, "COMPLETED")
        tools = [step.tool for step in result.steps]
        self.assertIn("get_dataset_schema", tools)
        self.assertIn("range_query", tools)
        step = next(step for step in result.steps if step.tool == "get_zonal_raster_statistics")
        self.assertEqual(step.args["admin_name"], "洪山区")
        self.assertGreater(step.result["statistics"]["valid_pixel_count"], 0)
        contract = build_result_contract({**result.to_dict(), "result_type": result.plan.output["type"]})
        self.assertEqual(contract["type"], result.plan.output["type"])
        self.assertTrue(contract["data"]["evidence_steps"])


if __name__ == "__main__":
    unittest.main()
