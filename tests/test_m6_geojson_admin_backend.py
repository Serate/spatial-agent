import importlib.util
import unittest
from pathlib import Path

from agent.dataset_catalog import DatasetCatalog
from agent.spatial_backend import GeoJSONAdminBackend, HybridSpatialBackend


ROOT = Path(__file__).parents[1]
HAS_GIS = importlib.util.find_spec("geopandas") is not None
HAS_LOCAL_DATA = Path("D:/dataset/agent/湖北省_县.geojson").exists()


@unittest.skipUnless(HAS_GIS and HAS_LOCAL_DATA, "requires geopandas and local admin GeoJSON")
class M6GeoJSONAdminBackendTests(unittest.TestCase):
    def build_backend(self):
        catalog = DatasetCatalog.from_json(str(ROOT / "config" / "datasets.local.example.json"))
        return GeoJSONAdminBackend(catalog)

    def test_schema_comes_from_real_geojson(self):
        schema = self.build_backend().get_dataset_schema("admin_areas")
        self.assertEqual(schema["dataset"], "admin_areas")
        self.assertEqual(schema["crs"], "EPSG:4490")
        self.assertIn("name", schema["fields"])
        self.assertEqual(schema["metrics"]["feature_count"], 103)

    def test_range_query_filters_by_county_name(self):
        result = self.build_backend().range_query(
            "admin_areas",
            [{"field": "name", "operator": "eq", "value": "洪山区"}],
            10,
        )
        self.assertEqual(result["result_ref"], "geojson://range/admin_areas")
        self.assertEqual(result["count"], 1)
        self.assertIn("洪山区", result["sample_names"])
        self.assertEqual(result["metrics"]["backend"], "geojson")

    def test_hybrid_backend_uses_real_admin_and_memory_fallback(self):
        catalog = DatasetCatalog.from_json(str(ROOT / "config" / "datasets.local.example.json"))
        backend = HybridSpatialBackend(catalog)
        admin_schema = backend.get_dataset_schema("admin_areas")
        road_schema = backend.get_dataset_schema("roads")
        self.assertEqual(admin_schema["metrics"]["backend"], "geojson")
        self.assertEqual(road_schema["geometry_type"], "LineString")


if __name__ == "__main__":
    unittest.main()
