import importlib.util
import unittest
from pathlib import Path

from agent.answer_composer import AnswerComposer
from agent.models import AgentRunResult, RunStatus, StepRun
from agent.planner import RuleBasedPlanner


ROOT = Path(__file__).parents[1]
HAS_GIS_DATA = importlib.util.find_spec("geopandas") is not None and Path("D:/tmp/wuhan-gis/wuhan-osm.gpkg").exists()


class VectorPlanningTests(unittest.TestCase):
    def test_rule_planner_creates_water_query(self):
        plan = RuleBasedPlanner().plan("查询武汉水体")
        self.assertEqual([step.tool for step in plan.steps], ["get_dataset_schema", "range_query"])
        self.assertEqual(plan.steps[1].args["dataset"], "water")

    def test_rule_planner_creates_zonal_vector_summary(self):
        plan = RuleBasedPlanner().plan("查询洪山区道路")
        self.assertEqual([step.tool for step in plan.steps], ["get_zonal_vector_summary"])
        self.assertEqual(plan.steps[0].args["admin_name"], "洪山区")

    def test_rule_planner_creates_road_water_near_join(self):
        plan = RuleBasedPlanner().plan("查询距离水体500米以内的道路")
        self.assertEqual([step.tool for step in plan.steps], ["get_dataset_schema", "get_dataset_schema", "spatial_join"])
        self.assertEqual(plan.steps[-1].args["right_dataset"], "water")

    def test_rule_planner_creates_constrained_buildability_plan(self):
        plan = RuleBasedPlanner().plan("分析洪山区建设适宜性，坡度不超过20度，距离道路500米以内，避开水体")
        self.assertEqual(
            [step.tool for step in plan.steps],
            ["get_dataset_health_report", "get_zonal_constrained_buildability_analysis"],
        )
        self.assertEqual(plan.steps[1].args["slope_limit_degrees"], 20.0)
        self.assertTrue(plan.steps[1].args["exclude_water"])
        self.assertEqual(plan.steps[1].depends_on, ["dataset-health"])

    def test_vector_answer_mentions_osm_limit(self):
        result = AgentRunResult(
            run_id="test-vector",
            status=RunStatus.COMPLETED,
            request="查询武汉道路",
            plan=RuleBasedPlanner().plan("查询武汉道路"),
            steps=[
                StepRun(id="schema", tool="get_dataset_schema", args={"dataset": "roads"}, status="COMPLETED", result={"dataset": "roads", "crs": "EPSG:4326", "fields": []}),
                StepRun(id="query", tool="range_query", args={"dataset": "roads"}, status="COMPLETED", result={"dataset": "roads", "count": 4, "crs": "EPSG:4326", "metrics": {"source": "wuhan-osm.gpkg"}}),
            ],
        )
        answer = AnswerComposer().compose(result)
        self.assertIn("4", answer)
        self.assertIn("OpenStreetMap", answer)

    def test_constrained_answer_mentions_health_preflight(self):
        result = AgentRunResult(
            run_id="preflight-test",
            status=RunStatus.COMPLETED,
            request="联合建设筛选",
            plan=RuleBasedPlanner().plan("分析洪山区建设适宜性，坡度不超过20度，距离道路500米以内，避开水体"),
            steps=[
                StepRun(
                    id="health",
                    tool="get_dataset_health_report",
                    args={"dataset": "all"},
                    status="COMPLETED",
                    result={"status": "degraded", "relationships": {"dem_land_use": {"overlapping_pairs": 25}}},
                ),
                StepRun(
                    id="constrained",
                    tool="get_zonal_constrained_buildability_analysis",
                    args={},
                    status="COMPLETED",
                    result={
                        "admin_name": "洪山区",
                        "statistics": {"candidate_ratio": 0.1},
                        "constraint_summary": {"candidate_features": 2, "eligible_features": 1, "water_excluded_features": 0, "road_distance_m": 500},
                    },
                ),
            ],
        )
        answer = AnswerComposer().compose(result)
        self.assertIn("数据预检", answer)
        self.assertIn("25", answer)


@unittest.skipUnless(HAS_GIS_DATA, "requires generated Wuhan GIS data")
class RealVectorWorkflowTests(unittest.TestCase):
    def test_real_query_can_be_planned_and_executed(self):
        from run_demo import build_runtime

        old = __import__("os").environ.get("SPATIAL_AGENT_DATASET_CONFIG")
        __import__("os").environ["SPATIAL_AGENT_DATASET_CONFIG"] = str(ROOT / "config" / "datasets.wuhan.local.example.json")
        try:
            result = build_runtime("rule", "local").run("查询武汉主干道")
        finally:
            if old is None:
                __import__("os").environ.pop("SPATIAL_AGENT_DATASET_CONFIG", None)
            else:
                __import__("os").environ["SPATIAL_AGENT_DATASET_CONFIG"] = old
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.steps[-1].result["metrics"]["backend"], "geopackage")
        self.assertGreater(result.steps[-1].result["count"], 0)
        self.assertIn("OpenStreetMap", result.answer)

    def test_real_zonal_vector_summary_returns_categories(self):
        from agent.dataset_catalog import DatasetCatalog
        from agent.spatial_backend import HybridSpatialBackend

        backend = HybridSpatialBackend(DatasetCatalog.from_json(str(ROOT / "config" / "datasets.wuhan.local.example.json")))
        result = backend.get_zonal_vector_summary("roads", "洪山区", max_features=1000)
        self.assertEqual(result["metrics"]["backend"], "geopackage")
        self.assertGreater(result["summary"]["matched_features"], 0)
        self.assertTrue(result["summary"]["category_counts"])

    def test_real_road_water_near_join(self):
        from agent.dataset_catalog import DatasetCatalog
        from agent.spatial_backend import GeoPackageBackend

        backend = GeoPackageBackend(DatasetCatalog.from_json(str(ROOT / "config" / "datasets.wuhan.local.example.json")))
        result = backend.spatial_join("roads", "water", "near", 500)
        self.assertEqual(result["metrics"]["backend"], "geopackage")
        self.assertGreater(result["count"], 0)

    def test_real_constrained_buildability_returns_sample_summary(self):
        from agent.dataset_catalog import DatasetCatalog
        from agent.spatial_backend import HybridSpatialBackend

        backend = HybridSpatialBackend(DatasetCatalog.from_json(str(ROOT / "config" / "datasets.wuhan.local.example.json")))
        result = backend.get_zonal_constrained_buildability_analysis("洪山区", slope_limit_degrees=20, road_distance_m=500, exclude_water=True, max_files=10)
        self.assertEqual(result["metrics"]["constraint_sampled"], True)
        self.assertIn("eligible_features", result["constraint_summary"])
        self.assertTrue(result["result_ref"].startswith("raster://"))
        exported = backend.export_result(result["result_ref"], max_features=3)
        self.assertEqual(exported["crs"]["properties"]["name"], "EPSG:4326")
        self.assertEqual(exported["source_crs"], "EPSG:4326")
        self.assertGreater(len(exported["features"]), 0)


if __name__ == "__main__":
    unittest.main()
