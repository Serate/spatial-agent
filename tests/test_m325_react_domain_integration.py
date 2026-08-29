import unittest

from agent.models import PlanStep, TaskPlan
from domains.gis.domain import GisDomainPack


class M325ReactDomainIntegrationTests(unittest.TestCase):
    def test_health_preflight_is_allowed_before_single_result_workflow(self):
        plan = TaskPlan(
            "读取 DEM 元数据",
            steps=[
                PlanStep(
                    "health",
                    "get_dataset_health_report",
                    {"dataset": "all", "max_files": 10},
                ),
                PlanStep(
                    "metadata",
                    "get_raster_metadata",
                    {"dataset": "dem", "max_files": 3},
                    ["health"],
                ),
            ],
            output={"type": "raster_metadata_result"},
        )

        GisDomainPack().validate_plan(plan)
        policy = GisDomainPack().plan_policy(plan)
        self.assertIn("get_dataset_health_report", policy["allowed_tools"])
        self.assertEqual(policy["max_steps"], 2)


if __name__ == "__main__":
    unittest.main()
