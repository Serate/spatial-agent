import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from domains.gis.adapters.data_quality import dataset_health_report
from domains.gis.adapters.dataset_catalog import DatasetCatalog, DatasetEntry
from agent.runtime_capabilities import runtime_capability_snapshot


class M67DataProvenanceTests(unittest.TestCase):
    def test_dataset_entry_keeps_optional_provenance_and_omits_empty_values(self):
        entry = DatasetEntry(
            name="roads",
            kind="vector",
            format="gpkg",
            role="roads",
            files=[],
            source=" OpenStreetMap\n",
            version="2026-08-08",
            attribution="© OpenStreetMap contributors",
            license="ODbL 1.0",
        )

        self.assertEqual(
            entry.provenance,
            {
                "source": "OpenStreetMap",
                "version": "2026-08-08",
                "attribution": "© OpenStreetMap contributors",
                "license": "ODbL 1.0",
            },
        )
        self.assertEqual(entry.to_dict()["source"], "OpenStreetMap")

        legacy = DatasetEntry("legacy", "vector", "geojson", "demo", [])
        self.assertEqual(legacy.provenance, {})
        self.assertNotIn("source", legacy.to_dict())

    def test_provenance_is_allowlisted_bounded_and_scalar(self):
        entry = DatasetEntry(
            "dem",
            "raster",
            "img",
            "dem",
            [],
            source="x\x00\n" + ("s" * 400),
            version={"secret": "must not escape"},
            attribution=["invalid"],
            license="  demo license  ",
        )

        self.assertEqual(set(entry.provenance), {"source", "license"})
        self.assertLessEqual(len(entry.provenance["source"]), 256)
        self.assertNotIn("\n", entry.provenance["source"])
        self.assertEqual(entry.provenance["license"], "demo license")

    def test_legacy_json_without_metadata_still_loads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "legacy-datasets.json"
            config_path.write_text(
                json.dumps(
                    {
                        "root": temp_dir,
                        "datasets": {
                            "admin_areas": {
                                "kind": "vector",
                                "format": "geojson",
                                "path": "missing.geojson",
                                "role": "legacy boundary",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            entry = DatasetCatalog.from_json(str(config_path)).require("admin_areas")

        self.assertEqual(entry.provenance, {})
        self.assertEqual(entry.role, "legacy boundary")
        self.assertEqual(entry.files, [])

    def test_health_report_exposes_dataset_and_summary_provenance(self):
        entries = {
            "dem": DatasetEntry(
                "dem", "raster", "img", "dem", [], source="ASTER GDEM", version="v3"
            ),
        }
        report = dataset_health_report(DatasetCatalog("unused", entries), max_files=1)

        dem = next(item for item in report["datasets"] if item["dataset"] == "dem")
        roads = next(item for item in report["datasets"] if item["dataset"] == "roads")
        self.assertEqual(dem["provenance"], {"source": "ASTER GDEM", "version": "v3"})
        self.assertEqual(report["provenance"]["dem"], dem["provenance"])
        self.assertEqual(roads["provenance"], {})

    def test_pending_entry_is_reported_without_expensive_probe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "pending.zip"
            path.write_bytes(b"archive")
            catalog = DatasetCatalog(
                temp_dir,
                {
                    "dem": DatasetEntry(
                        "dem", "raster", "zip", "pending DEM", [str(path)],
                        status="pending", availability_reason="等待解压和 CRS 核验",
                    ),
                },
            )
            report = dataset_health_report(catalog, dataset="dem", max_files=1)

        dem = report["datasets"][0]
        self.assertEqual(dem["status"], "pending")
        self.assertTrue(dem["metrics"]["deferred"])
        self.assertIn("等待解压", dem["checks"][0]["message"])

    def test_runtime_snapshot_propagates_only_controlled_provenance(self):
        health = {
            "status": "ready",
            "core_status": "ready",
            "optional_status": "unavailable",
            "updated_at": "2026-08-10T00:00:00Z",
            "datasets": [
                {
                    "dataset": "dem",
                    "status": "ready",
                    "bounds": [1, 2, 3, 4],
                    "crs_values": ["EPSG:4326"],
                    "file_count": 1,
                    "metrics": {"checked_files": 1},
                    "provenance": {
                        "source": "ASTER GDEM",
                        "version": "v3",
                        "api_key": "must not escape",
                    },
                    "usable_for": ["get_raster_metadata"],
                },
            ],
            "capabilities": {"dem": ["get_raster_metadata"]},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "datasets.json"
            config_path.write_text(json.dumps({"root": temp_dir, "datasets": {}}), encoding="utf-8")
            with patch.dict(os.environ, {"SPATIAL_AGENT_DATASET_CONFIG": str(config_path)}), patch(
                "domains.gis.adapters.runtime_capabilities.environment_status",
                return_value={
                    "capabilities": {"local_gis_backend": False},
                    "dependencies": {"geopandas": False, "rasterio": False},
                },
            ), patch("domains.gis.adapters.runtime_capabilities.dataset_health_report", return_value=health):
                snapshot = runtime_capability_snapshot(max_files=1)

        expected = {"source": "ASTER GDEM", "version": "v3"}
        self.assertEqual(snapshot["data_provenance"]["dem"], expected)
        self.assertEqual(snapshot["data_evidence"]["dem"]["provenance"], expected)
        raster = next(item for item in snapshot["capabilities"] if item["id"] == "raster_metadata")
        self.assertEqual(raster["runtime_evidence"]["datasets"]["dem"]["provenance"], expected)
        self.assertNotIn("api_key", json.dumps(snapshot, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
