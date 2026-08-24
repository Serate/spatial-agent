import unittest
from pathlib import Path

from agent.errors import ToolError
from agent.planner import RuleBasedPlanner
from agent.spatial_backend import GeoPackageBackend, InMemorySpatialBackend, SpatialToolAdapter
from agent.tools import ToolRegistry


ROOT = Path(__file__).parents[1]


class M247SpatialOperationTests(unittest.TestCase):
    def test_domain_catalog_and_workflow_share_operation_contract(self):
        from domains.gis.catalog import GIS_CAPABILITIES
        from domains.gis.workflow_templates import workflow_template_catalog

        capability = next(item for item in GIS_CAPABILITIES if item["id"] == "vector_operation")
        template = workflow_template_catalog()["vector_operation"]
        self.assertEqual(capability["tools"], ["spatial_operation"])
        self.assertEqual(template["allowed_tools"], ["spatial_operation"])
        self.assertEqual(template["output_template"]["type"], "spatial_operation_result")

    def test_rule_planner_composes_region_masked_operation(self):
        plan = RuleBasedPlanner().plan("裁剪洪山区道路")
        self.assertEqual(plan.steps[-1].tool, "spatial_operation")
        self.assertEqual(plan.steps[-1].args["input_ref"], "roads")
        self.assertEqual(plan.steps[-1].args["operation"], "clip")
        self.assertEqual(plan.steps[-1].depends_on, ["filter-admin"])

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


if __name__ == "__main__":
    unittest.main()
