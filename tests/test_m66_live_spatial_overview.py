import os
import unittest

from run_demo import build_runtime


@unittest.skipUnless(
    os.environ.get("SPATIAL_AGENT_LIVE_OPENAI") == "1"
    and os.environ.get("SPATIAL_AGENT_LIVE_GIS") == "1",
    "set SPATIAL_AGENT_LIVE_OPENAI=1 and SPATIAL_AGENT_LIVE_GIS=1 to run live overview GIS smoke",
)
class M66LiveSpatialOverviewTests(unittest.TestCase):
    def test_live_model_plans_and_executes_spatial_overview(self):
        result = None
        failures = []
        for _ in range(3):
            candidate = build_runtime("openai", "local").run("分析洪山区空间概况")
            if candidate.status.value == "COMPLETED":
                result = candidate
                break
            failures.append(candidate.error or candidate.status.value)
        if result is None:
            self.fail("空间总览 live 请求连续失败：" + " | ".join(failures))

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "spatial_overview_result")
        expected = {
            "get_dataset_health_report",
            "get_dataset_schema",
            "range_query",
            "get_zonal_raster_statistics",
            "get_zonal_slope_statistics",
            "get_zonal_land_use_distribution",
            "get_zonal_vector_summary",
        }
        self.assertTrue(expected.issubset({step.tool for step in result.steps}))
        self.assertTrue(all(step.status == "COMPLETED" for step in result.steps))
        self.assertIn("洪山区", result.answer)


if __name__ == "__main__":
    unittest.main()
