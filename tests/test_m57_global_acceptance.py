import json
import unittest
from pathlib import Path

from agent.service import AgentService
from run_demo import build_runtime


ROOT = Path(__file__).parents[1]


class M57GlobalAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(
            (ROOT / "evaluation" / "cases" / "global-acceptance.json").read_text(
                encoding="utf-8"
            )
        )

    def test_matrix_covers_global_surfaces(self):
        surfaces = {case["surface"] for case in self.cases}
        categories = {case["category"] for case in self.cases}
        self.assertTrue({"runtime", "comparison-api", "runtime-contract"} <= surfaces)
        self.assertTrue({"通用问答", "单区域", "多数据集", "阈值对比", "多区域", "不可用数据", "真实 GIS", "真实模型"} <= categories)

    def test_offline_runtime_cases_match_matrix(self):
        runtime_cases = [case for case in self.cases if case["surface"] == "runtime"]
        runtime = build_runtime("rule", "memory")
        for case in runtime_cases:
            with self.subTest(case=case["id"]):
                result = runtime.run(case["input"], session_id="global-" + case["id"])
                self.assertEqual(result.status.value, case["expected_status"])
                if case["expected_result_type"] is None:
                    self.assertIsNone(result.plan)
                else:
                    self.assertEqual(result.plan.output.get("type"), case["expected_result_type"])
                self.assertEqual([step.tool for step in result.steps], case["expected_tools"])

    def test_comparison_api_cases_return_normalized_scenario(self):
        service = AgentService()
        threshold_case = next(case for case in self.cases if case["id"] == "threshold-comparison")
        region_case = next(case for case in self.cases if case["id"] == "region-comparison")
        threshold = service.compare_buildability(**threshold_case["input"], backend="memory")
        regions = service.compare_buildability_regions(**region_case["input"], backend="memory")
        self.assertEqual(threshold["scenario"]["operation"], "buildability_comparison")
        self.assertEqual(regions["scenario"]["operation"], "buildability_comparison")
        self.assertEqual(regions["scenario"]["admin_names"], region_case["input"]["admin_names"])


if __name__ == "__main__":
    unittest.main()
