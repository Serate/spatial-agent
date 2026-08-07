import json
import unittest
from pathlib import Path

from run_demo import build_runtime


ROOT = Path(__file__).parents[1]


class M44CoreWorkflowAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(
            (ROOT / "evaluation" / "cases" / "core-workflows.json").read_text(
                encoding="utf-8"
            )
        )

    def test_three_core_spatial_workflows_keep_expected_tool_contracts(self):
        runtime = build_runtime("rule", "memory")
        for case in self.cases:
            with self.subTest(case=case["id"]):
                result = runtime.run(case["input"], session_id="core-" + case["id"])
                self.assertEqual(result.status.value, case["expected_status"])
                self.assertEqual(
                    [step.tool for step in result.steps], case["expected_tools"]
                )
                self.assertTrue(result.answer)
                self.assertTrue(result.plan)

    def test_core_workflows_support_clarification_and_follow_up(self):
        runtime = build_runtime("rule", "memory")
        first = runtime.run("查询行政区边界", session_id="core-follow-up")
        second = runtime.run("洪山区", session_id="core-follow-up")

        self.assertEqual(first.status.value, "NEEDS_CLARIFICATION")
        self.assertEqual(second.status.value, "COMPLETED")
        self.assertIn("洪山区", second.resolved_request)
        self.assertEqual([step.tool for step in second.steps], [
            "get_dataset_schema",
            "range_query",
        ])

    def test_core_boundary_rejects_unsupported_spatial_domain(self):
        result = build_runtime("rule", "memory").run("分析洪山区空气质量变化")

        self.assertEqual(result.status.value, "NEEDS_CLARIFICATION")
        self.assertEqual(result.steps, [])
        self.assertIsNone(result.answer)

    def test_natural_language_variants_preserve_the_same_workflows(self):
        runtime = build_runtime("rule", "memory")
        variants = {
            "洪山区地形怎么样": ["get_zonal_raster_statistics"],
            "查看洪山区土地覆盖情况": ["get_zonal_raster_statistics"],
            "洪山区有哪些地方适合建设": [
                "get_dataset_schema",
                "range_query",
                "get_zonal_raster_statistics",
                "get_zonal_slope_statistics",
                "get_zonal_land_use_distribution",
                "get_zonal_buildability_analysis",
            ],
        }
        for request, expected_tools in variants.items():
            with self.subTest(request=request):
                result = runtime.run(request, session_id="variant-" + request)
                self.assertEqual(result.status.value, "COMPLETED")
                self.assertEqual([step.tool for step in result.steps], expected_tools)
                self.assertEqual(result.steps[-1].args.get("admin_name"), "洪山区")


if __name__ == "__main__":
    unittest.main()
