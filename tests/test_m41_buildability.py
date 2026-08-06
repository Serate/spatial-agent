import unittest

from run_demo import build_runtime


class M41BuildabilityTests(unittest.TestCase):
    def test_rule_planner_accepts_direct_buildability_request(self):
        result = build_runtime("rule", "memory").run(
            "分析洪山区建设适宜性，坡度不超过20度"
        )

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(
            [step.tool for step in result.steps],
            [
                "get_dataset_schema",
                "range_query",
                "get_zonal_raster_statistics",
                "get_zonal_slope_statistics",
                "get_zonal_land_use_distribution",
                "get_zonal_buildability_analysis",
            ],
        )
        self.assertEqual(result.steps[-1].args["slope_limit_degrees"], 20.0)
        self.assertIn("建设候选", result.answer)

    def test_default_buildability_threshold_is_explicit(self):
        result = build_runtime("rule", "memory").run("分析洪山区建设适宜性")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.steps[-1].args["slope_limit_degrees"], 15.0)


if __name__ == "__main__":
    unittest.main()
