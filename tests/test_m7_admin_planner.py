import importlib.util
import unittest
from pathlib import Path

from agent.planner import RuleBasedPlanner
from run_demo import build_runtime


HAS_GIS = importlib.util.find_spec("geopandas") is not None
HAS_LOCAL_DATA = Path("D:/dataset/agent/\u6e56\u5317\u7701_\u53bf.geojson").exists()
ADMIN_QUERY = "\u67e5\u8be2\u6d2a\u5c71\u533a\u884c\u653f\u533a\u8fb9\u754c"
GENERIC_ADMIN_QUERY = "\u67e5\u8be2\u884c\u653f\u533a\u8fb9\u754c"
ADMIN_NAME = "\u6d2a\u5c71\u533a"


class M7AdminPlannerTests(unittest.TestCase):
    def test_rule_planner_generates_admin_area_query(self):
        plan = RuleBasedPlanner().plan(ADMIN_QUERY)
        self.assertEqual(plan.goal, "query admin area boundary by name")
        self.assertEqual([step.tool for step in plan.steps], ["get_dataset_schema", "range_query"])
        self.assertEqual(plan.steps[1].args["dataset"], "admin_areas")
        self.assertEqual(plan.steps[1].args["conditions"][0]["value"], ADMIN_NAME)

    def test_rule_planner_asks_for_admin_name(self):
        result = build_runtime("rule").run(GENERIC_ADMIN_QUERY)
        self.assertEqual(result.status.value, "NEEDS_CLARIFICATION")
        self.assertIn("admin area name", result.error)


@unittest.skipUnless(HAS_GIS and HAS_LOCAL_DATA, "requires geopandas and local admin GeoJSON")
class M7AdminPlannerLocalBackendTests(unittest.TestCase):
    def test_runtime_queries_real_admin_area_by_name(self):
        result = build_runtime("rule", "local").run(ADMIN_QUERY)
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.steps[1].result["result_ref"], "geojson://range/admin_areas")
        self.assertEqual(result.steps[1].result["count"], 1)
        self.assertIn(ADMIN_NAME, result.steps[1].result["sample_names"])


if __name__ == "__main__":
    unittest.main()
