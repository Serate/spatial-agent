import os
import unittest

from run_demo import build_runtime


@unittest.skipUnless(
    os.environ.get("SPATIAL_AGENT_LIVE_OPENAI") == "1",
    "set SPATIAL_AGENT_LIVE_OPENAI=1 to run live zonal planner smoke",
)
class M29LiveZonalAnalysisTests(unittest.TestCase):
    def test_live_model_plans_and_executes_zonal_dem_analysis(self):
        result = build_runtime("openai", "local").run("分析洪山区DEM高程概况")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertTrue(result.steps)
        self.assertEqual(result.steps[0].tool, "get_zonal_raster_statistics")
        statistics = result.steps[0].result["statistics"]
        self.assertIsNone(statistics.get("error"))
        self.assertGreater(statistics["valid_pixel_count"], 0)
        self.assertIn("洪山区", result.answer)

    def test_live_model_plans_composite_admin_raster_analysis(self):
        result = build_runtime("openai", "local").run(
            "查询洪山区行政区边界并分析DEM高程概况"
        )

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(
            [step.tool for step in result.steps],
            ["get_dataset_schema", "range_query", "get_zonal_raster_statistics"],
        )
        self.assertEqual(result.steps[2].args["admin_name"], "洪山区")
        self.assertGreater(result.steps[2].result["statistics"]["valid_pixel_count"], 0)


if __name__ == "__main__":
    unittest.main()
