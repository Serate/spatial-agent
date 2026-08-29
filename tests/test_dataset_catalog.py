import unittest
from pathlib import Path

from domains.gis.adapters.dataset_catalog import DatasetCatalog, DatasetEntry


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

    def test_discovery_defaults_to_ready_and_supports_tags(self):
        catalog = DatasetCatalog(
            "unused",
            {
                "roads": DatasetEntry(
                    "roads", "vector", "gpkg", "roads", [],
                    status="ready", stage="staged", tags=("道路", "交通"),
                ),
                "archive": DatasetEntry(
                    "archive", "vector", "zip", "roads", [],
                    status="pending", stage="raw", tags=("道路",),
                ),
            },
        )

        self.assertEqual([entry.name for entry in catalog.discover(kind="vector")], ["roads"])
        self.assertEqual(
            [entry.name for entry in catalog.discover(required_tags=("交通",))],
            ["roads"],
        )
        self.assertEqual([entry.name for entry in catalog.discover(status=None)], ["archive", "roads"])

    def test_discovery_metadata_is_bounded_and_in_summary(self):
        entry = DatasetEntry(
            "dem", "raster", "tif", "elevation", [],
            status="ready", stage="analysis-ready", tags=("DEM", "DEM"),
            coverage="武汉", resolution="30 m",
        )
        catalog = DatasetCatalog("unused", {"dem": entry})
        self.assertEqual(entry.to_dict()["tags"], ["DEM"])
        self.assertEqual(catalog.discovery_summary()["ready_count"], 1)
        self.assertEqual(catalog.summary()["discovery"]["by_kind"], {"raster": 1})


if __name__ == "__main__":
    unittest.main()
