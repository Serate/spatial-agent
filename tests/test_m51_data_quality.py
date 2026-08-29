import importlib.util
import unittest
from pathlib import Path

from agent.answer_composer import AnswerComposer
from agent.models import AgentRunResult, RunStatus, StepRun
from agent.planner import RuleBasedPlanner
from agent.runtime import AgentRuntime
from domains.gis.adapters.spatial_backend import InMemorySpatialBackend, SpatialToolAdapter
from agent.tools import ToolRegistry


ROOT = Path(__file__).parents[1]
HAS_GIS_DATA = (
    importlib.util.find_spec("geopandas") is not None
    and importlib.util.find_spec("rasterio") is not None
    and Path("D:/tmp/wuhan-gis/wuhan-osm.gpkg").exists()
)


class DataQualityContractTests(unittest.TestCase):
    def test_rule_planner_selects_health_tool_for_general_quality_request(self):
        plan = RuleBasedPlanner().plan("检查武汉空间数据质量")
        self.assertEqual([step.tool for step in plan.steps], ["get_dataset_health_report"])
        self.assertEqual(plan.steps[0].args["dataset"], "all")

    def test_rule_planner_selects_named_dataset(self):
        plan = RuleBasedPlanner().plan("检查DEM数据是否可用")
        self.assertEqual(plan.steps[0].args["dataset"], "dem")

    def test_memory_health_report_is_explicitly_degraded(self):
        result = SpatialToolAdapter(InMemorySpatialBackend()).invoke(
            "get_dataset_health_report", {"dataset": "all", "max_files": 10}
        )
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(len(result["datasets"]), 5)
        self.assertTrue(all(item["errors"] for item in result["datasets"]))
        self.assertTrue(all(item["usable_for"] == [] for item in result["datasets"]))

    def test_real_health_report_declares_operation_capabilities(self):
        from domains.gis.adapters.data_quality import DATASET_CAPABILITIES

        self.assertIn("get_zonal_slope_statistics", DATASET_CAPABILITIES["dem"])
        self.assertIn("get_zonal_land_use_distribution", DATASET_CAPABILITIES["land_use"])
        self.assertIn("get_zonal_vector_summary", DATASET_CAPABILITIES["roads"])

    def test_unavailable_preflight_stops_raster_tool_before_dispatch(self):
        class MissingRasterBackend(InMemorySpatialBackend):
            def get_dataset_health_report(self, dataset="all", max_files=10):
                return {
                    "dataset": "all",
                    "status": "unavailable",
                    "datasets": [
                        {"dataset": "dem", "status": "unavailable", "usable_for": [], "errors": ["缺少 DEM"]},
                        {"dataset": "land_use", "status": "unavailable", "usable_for": [], "errors": ["缺少土地利用"]},
                    ],
                    "capabilities": {"dem": [], "land_use": []},
                }

        class FixedPlanner:
            def plan(self, request):
                from agent.models import PlanStep, TaskPlan

                return TaskPlan(
                    goal="preflight gate",
                    steps=[
                        PlanStep("health", "get_dataset_health_report", {"dataset": "all"}),
                        PlanStep(
                            "zonal",
                            "get_zonal_raster_statistics",
                            {"dataset": "dem", "admin_name": "洪山区"},
                            ["health"],
                        ),
                    ],
                    output={"type": "zonal_raster_statistics_result"},
                )

        registry = ToolRegistry.from_json(
            str(ROOT / "tools" / "schema" / "tool-definitions.json"),
            SpatialToolAdapter(MissingRasterBackend()),
        )
        result = AgentRuntime(FixedPlanner(), registry).run("测试不可用栅格")
        self.assertEqual(result.status.value, "FAILED")
        self.assertIn("数据预检阻止工具", result.error)
        self.assertIn("数据", result.answer)
        self.assertEqual(result.steps[1].status, "FAILED")

    def test_answer_composer_explains_health_status(self):
        result = AgentRunResult(
            run_id="health-test",
            status=RunStatus.COMPLETED,
            request="检查数据质量",
            plan=RuleBasedPlanner().plan("检查武汉空间数据质量"),
            steps=[
                StepRun(
                    id="health",
                    tool="get_dataset_health_report",
                    args={"dataset": "all"},
                    status="COMPLETED",
                    result={
                        "dataset": "all",
                        "status": "degraded",
                        "datasets": [{"dataset": "dem", "status": "degraded", "file_count": 0, "errors": ["未连接本地数据文件"]}],
                    },
                )
            ],
        )
        self.assertIn("部分可用", AnswerComposer().compose(result))


@unittest.skipUnless(HAS_GIS_DATA, "requires generated Wuhan GIS data and GIS dependencies")
class RealDataQualityTests(unittest.TestCase):
    def test_wuhan_catalog_reports_all_sources(self):
        from domains.gis.adapters.dataset_catalog import DatasetCatalog
        from domains.gis.adapters.data_quality import dataset_health_report

        catalog = DatasetCatalog.from_json(str(ROOT / "config" / "datasets.wuhan.local.example.json"))
        result = dataset_health_report(catalog, max_files=10)
        self.assertEqual(result["status"], "degraded")
        reports = {item["dataset"]: item for item in result["datasets"]}
        self.assertTrue({"admin_areas", "dem", "land_use", "roads", "water", "earthquakes_wuhan"}.issubset(reports))
        self.assertGreater(reports["roads"]["feature_count"], 0)
        self.assertGreater(reports["water"]["feature_count"], 0)
        self.assertTrue(reports["dem"]["crs_values"])
        self.assertEqual(reports["admin_areas"]["invalid_geometry_count"], 0)
        self.assertEqual(reports["roads"]["status"], "ready")
        self.assertEqual(reports["water"]["status"], "ready")
        self.assertEqual(reports["dem"]["status"], "degraded")
        self.assertTrue(any(check["name"] == "crs_consistency" for check in reports["dem"]["checks"]))
        alignment = result["relationships"]["dem_land_use"]
        self.assertEqual(alignment["status"], "ready")
        self.assertGreater(alignment["overlapping_pairs"], 0)
        self.assertEqual(alignment["grid_alignment"]["status"], "grid_mismatch")
        self.assertNotIn("get_zonal_buildability_analysis", result["capabilities"]["dem"])
        self.assertNotIn("get_zonal_buildability_analysis", result["capabilities"]["land_use"])


if __name__ == "__main__":
    unittest.main()
