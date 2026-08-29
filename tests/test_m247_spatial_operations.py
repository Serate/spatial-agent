import unittest
from pathlib import Path

from agent.errors import ToolError
from agent.planner import RuleBasedPlanner
from domains.gis.adapters.spatial_backend import GeoPackageBackend, InMemorySpatialBackend, SpatialToolAdapter
from agent.tools import ToolRegistry


ROOT = Path(__file__).parents[1]


class M247SpatialOperationTests(unittest.TestCase):
    def test_spatial_relation_view_renders_without_operation_argument(self):
        from domains.gis.views import build_views

        views = build_views(
            "spatial_relation_result",
            steps=[
                {
                    "id": "relation",
                    "tool": "spatial_join",
                    "args": {
                        "left_dataset": "roads",
                        "right_dataset": "water",
                    },
                    "result": {
                        "left_dataset": "roads",
                        "right_dataset": "water",
                        "count": 1,
                        "relation": "intersects",
                    },
                }
            ],
            geometry_evidence={},
            workspace={"panels": ["vector"]},
        )

        self.assertEqual(views["panels"]["vector"]["kind"], "spatial_relation")
        self.assertEqual(views["panels"]["vector"]["metrics"][0]["value"], 1)

    def test_domain_catalog_and_workflow_share_operation_contract(self):
        from domains.gis.catalog import GIS_CAPABILITIES
        from domains.gis.workflow_templates import workflow_template_catalog

        capability = next(item for item in GIS_CAPABILITIES if item["id"] == "vector_operation")
        template = workflow_template_catalog()["vector_operation"]
        self.assertEqual(capability["tools"], ["spatial_operation"])
        self.assertEqual(template["allowed_tools"], ["spatial_operation"])
        self.assertEqual(template["output_template"]["type"], "spatial_operation_result")
        self.assertEqual(
            workflow_template_catalog()["vector_measurement"]["required_constraints"],
            ["operation", "input_ref", "mask_ref", "distance_m"],
        )
        compiled = RuleBasedPlanner().plan(
            "空间距离分析",
            workflow={
                "template_id": "vector_measurement",
                "constraints": {
                    "operation": "distance",
                    "input_ref": "roads",
                    "mask_ref": "water",
                    "distance_m": 500,
                },
            },
        )
        self.assertEqual(compiled.steps[0].tool, "spatial_operation")
        self.assertEqual(compiled.steps[0].args["distance_m"], 500.0)

    def test_rule_planner_composes_region_masked_operation(self):
        plan = RuleBasedPlanner().plan("裁剪洪山区道路")
        self.assertEqual(plan.steps[-1].tool, "spatial_operation")
        self.assertEqual(plan.steps[-1].args["input_ref"], "roads")
        self.assertEqual(plan.steps[-1].args["operation"], "clip")
        self.assertEqual(plan.steps[-1].depends_on, ["filter-admin"])

    def test_rule_planner_composes_buffer_and_dataset_distance(self):
        buffered = RuleBasedPlanner().plan("对洪山区道路做500米缓冲")
        self.assertEqual(buffered.steps[-1].args["operation"], "buffer")
        self.assertEqual(buffered.steps[-1].args["distance_m"], 500.0)

        measured = RuleBasedPlanner().plan("计算道路与水体的最近距离")
        self.assertEqual(measured.steps[-1].args["operation"], "distance")
        self.assertEqual(measured.steps[-1].args["mask_ref"], "water")
        self.assertEqual(measured.steps[-1].depends_on, ["schema-input", "schema-mask"])

    def test_registry_exposes_bounded_operation_and_memory_fails_recoverably(self):
        registry = ToolRegistry.from_json(
            str(ROOT / "tools" / "schema" / "tool-definitions.json"),
            SpatialToolAdapter(InMemorySpatialBackend()),
        )
        with self.assertRaises(ToolError) as context:
            registry.invoke(
                "spatial_operation",
                {
                    "operation": "clip",
                    "input_ref": "roads",
                    "mask_ref": "admin_areas",
                },
            )
        self.assertEqual(context.exception.code, "vector_geometry_unavailable")

    def test_geopackage_operation_returns_vector_profile_and_export(self):
        import geopandas as gpd
        from shapely.geometry import Polygon

        backend = GeoPackageBackend.__new__(GeoPackageBackend)
        backend._entries = {}
        backend._cache = {}
        backend._result_cache = {
            "fixture-input": gpd.GeoDataFrame(
                {"name": ["road-a"]},
                geometry=[Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])],
                crs="EPSG:4326",
            ),
            "fixture-mask": gpd.GeoDataFrame(
                {"name": ["area-a"]},
                geometry=[Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])],
                crs="EPSG:4326",
            ),
        }
        backend._result_number = 0

        result = backend.spatial_operation(
            "clip", "fixture-input", "fixture-mask", max_features=10
        )

        self.assertEqual(result["operation"], "clip")
        self.assertEqual(result["data_profile"]["primary"], "vector")
        self.assertEqual(result["summary"]["intersecting_features"], 1)
        exported = backend.export_result(result["result_ref"], max_features=10)
        self.assertEqual(exported["type"], "FeatureCollection")
        self.assertEqual(len(exported["features"]), 1)

        buffered = backend.spatial_operation(
            "buffer", "fixture-input", "fixture-mask", max_features=10, distance_m=100
        )
        self.assertEqual(buffered["operation"], "buffer")
        self.assertEqual(buffered["summary"]["distance_m"], 100.0)
        self.assertGreaterEqual(buffered["count"], 1)

        measured = backend.spatial_operation(
            "distance", "fixture-input", "fixture-mask", max_features=10, distance_m=100
        )
        self.assertEqual(measured["operation"], "distance")
        self.assertIn("nearest_distance_mean_m", measured["summary"])
        self.assertGreaterEqual(measured["count"], 1)


if __name__ == "__main__":
    unittest.main()
