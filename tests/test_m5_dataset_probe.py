import importlib.util
import unittest
from pathlib import Path

from agent.dataset_catalog import DatasetCatalog
from agent.dataset_probe import probe_catalog


ROOT = Path(__file__).parents[1]
HAS_GIS = importlib.util.find_spec("geopandas") is not None and importlib.util.find_spec("rasterio") is not None
HAS_LOCAL_DATA = Path("D:/dataset/agent/湖北省_县.geojson").exists()


@unittest.skipUnless(HAS_GIS and HAS_LOCAL_DATA, "requires GIS dependencies and local dataset files")
class M5DatasetProbeTests(unittest.TestCase):
    def test_probe_catalog_reads_vector_and_raster_metadata(self):
        catalog = DatasetCatalog.from_json(str(ROOT / "config" / "datasets.local.example.json"))
        report = probe_catalog(catalog, max_files_per_dataset=2)
        by_name = {item["name"]: item for item in report["datasets"]}

        self.assertGreater(by_name["admin_areas"]["metadata"]["total_features"], 0)
        self.assertIn("name", by_name["admin_areas"]["metadata"]["fields"])
        self.assertEqual(by_name["dem"]["metadata"]["probed_files"], 2)
        self.assertGreater(by_name["dem"]["metadata"]["total_pixels"], 0)
        self.assertEqual(by_name["land_use"]["metadata"]["probed_files"], 2)


if __name__ == "__main__":
    unittest.main()
