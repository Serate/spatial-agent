import unittest

from agent.planner import RuleBasedPlanner
from agent.errors import ClarificationNeeded
from agent.spatial_intent import classify_spatial_intent
from run_demo import build_runtime


class M62SpatialIntentTests(unittest.TestCase):
    def test_classification_returns_hints_without_execution_claim(self):
        result = classify_spatial_intent("分析洪山区 DEM 空间分布")
        self.assertTrue(result["is_spatial"])
        self.assertIn("zonal_raster_statistics", result["matched_capabilities"])
        self.assertIn("suggested_capabilities", result)
        self.assertTrue(any(item["id"] == "admin_boundary_query" for item in result["suggested_capability_details"]))
        self.assertNotIn("status", result)

    def test_unknown_spatial_question_becomes_actionable_clarification(self):
        with self.assertRaisesRegex(ClarificationNeeded, "已识别为空间问题"):
            RuleBasedPlanner().plan("查询武汉城市绿地空间分布")

    def test_non_spatial_text_is_not_forced_into_gis(self):
        result = classify_spatial_intent("解释什么是空间数据库")
        self.assertTrue(result["is_spatial"])

    def test_runtime_exposes_structured_clarification(self):
        result = build_runtime("rule", "memory").run("查询武汉城市绿地空间分布")
        self.assertEqual(result.status.value, "NEEDS_CLARIFICATION")
        self.assertEqual(result.clarification["state"], "unmatched_spatial_capability")
        self.assertIn("区域", result.clarification["missing"])


if __name__ == "__main__":
    unittest.main()
