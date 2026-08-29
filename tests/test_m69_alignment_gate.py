import unittest
from pathlib import Path

from agent.models import PlanStep, TaskPlan
from agent.runtime import AgentRuntime
from domains.gis.adapters.spatial_backend import InMemorySpatialBackend, SpatialToolAdapter
from agent.tools import ToolRegistry


ROOT = Path(__file__).parents[1]


class MisalignedBackend(InMemorySpatialBackend):
    def __init__(self):
        super().__init__()
        self.buildability_called = False

    def get_dataset_health_report(self, dataset="all", max_files=10):
        return {
            "dataset": "all",
            "status": "degraded",
            "datasets": [
                {"dataset": "dem", "status": "ready", "usable_for": []},
                {"dataset": "land_use", "status": "ready", "usable_for": []},
            ],
            "capabilities": {"dem": [], "land_use": []},
            "relationships": {
                "dem_land_use": {
                    "grid_alignment": {
                        "status": "grid_mismatch",
                        "reason": "CRS differs",
                    }
                }
            },
        }

    def get_zonal_buildability_analysis(self, *args, **kwargs):
        self.buildability_called = True
        return super().get_zonal_buildability_analysis(*args, **kwargs)


class FixedBuildabilityPlanner:
    def plan(self, request):
        return TaskPlan(
            goal="像元级建设筛选",
            steps=[
                PlanStep("health", "get_dataset_health_report", {"dataset": "all"}),
                PlanStep(
                    "buildability",
                    "get_zonal_buildability_analysis",
                    {"admin_name": "洪山区", "slope_limit_degrees": 20},
                    ["health"],
                ),
            ],
            output={"type": "buildability_result", "summary": True},
        )


class M69AlignmentGateTests(unittest.TestCase):
    def test_explicit_grid_mismatch_blocks_joint_pixel_tool_before_dispatch(self):
        backend = MisalignedBackend()
        registry = ToolRegistry.from_json(
            str(ROOT / "tools" / "schema" / "tool-definitions.json"),
            SpatialToolAdapter(backend),
        )
        result = AgentRuntime(FixedBuildabilityPlanner(), registry).run("筛选")

        self.assertEqual(result.status.value, "FAILED")
        self.assertIn("像元级对齐门控阻止工具", result.error)
        self.assertEqual(result.steps[-1].status, "FAILED")
        self.assertFalse(backend.buildability_called)


if __name__ == "__main__":
    unittest.main()
