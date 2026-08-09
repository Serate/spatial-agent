import importlib.util
import unittest
from pathlib import Path

from agent.dataset_catalog import DatasetCatalog
from agent.spatial_backend import GeoPackageBackend, HybridSpatialBackend


ROOT = Path(__file__).parents[1]
HAS_GIS = importlib.util.find_spec("geopandas") is not None
HAS_GPKG = Path("D:/tmp/wuhan-gis/wuhan-osm.gpkg").exists()


@unittest.skipUnless(HAS_GIS and HAS_GPKG, "requires the generated Wuhan GeoPackage and GIS environment")
class M49GeoPackageBackendTests(unittest.TestCase):
    def build_catalog(self):
        return DatasetCatalog.from_json(str(ROOT / "config" / "datasets.wuhan.local.example.json"))

    def test_real_roads_schema_and_query(self):
        backend = GeoPackageBackend(self.build_catalog())
        schema = backend.get_dataset_schema("roads")
        self.assertEqual(schema["metrics"]["backend"], "geopackage")
        self.assertIn("highway", schema["fields"])
        result = backend.range_query("roads", [{"field": "road_level", "operator": "eq", "value": "primary"}], 5)
        self.assertGreater(result["count"], 0)
        self.assertTrue(result["result_ref"].startswith("gpkg://"))

    def test_hybrid_routes_water_to_real_backend(self):
        backend = HybridSpatialBackend(self.build_catalog())
        schema = backend.get_dataset_schema("water")
        self.assertEqual(schema["metrics"]["backend"], "geopackage")
        result = backend.range_query("water", [], 3)
        exported = backend.export_result(result["result_ref"], max_features=3)
        self.assertEqual(exported["type"], "FeatureCollection")
        self.assertGreater(len(exported["features"]), 0)


if __name__ == "__main__":
    unittest.main()
