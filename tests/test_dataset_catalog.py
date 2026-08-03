import unittest
from pathlib import Path

from agent.dataset_catalog import DatasetCatalog


ROOT = Path(__file__).parents[1]


class DatasetCatalogTests(unittest.TestCase):
    def test_catalog_loads_local_example(self):
        catalog = DatasetCatalog.from_json(str(ROOT / "config" / "datasets.local.example.json"))
        summary = catalog.summary()
        self.assertIn("datasets", summary)
        self.assertGreaterEqual(len(summary["datasets"]), 4)

    def test_catalog_resolves_known_dataset_names(self):
        catalog = DatasetCatalog.from_json(str(ROOT / "config" / "datasets.local.example.json"))
        self.assertEqual(catalog.require("admin_areas").kind, "vector")
        self.assertEqual(catalog.require("dem").kind, "raster")
        self.assertEqual(catalog.require("land_use").format, "tif")


if __name__ == "__main__":
    unittest.main()
