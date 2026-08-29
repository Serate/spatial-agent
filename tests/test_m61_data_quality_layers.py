import unittest
from unittest.mock import patch

from agent.capability_catalog import capability_catalog, runtime_capability_catalog
from domains.gis.adapters.data_quality import dataset_health_report
from domains.gis.adapters.dataset_catalog import DatasetCatalog


class M61DataQualityLayerTests(unittest.TestCase):
    def test_core_status_is_not_masked_by_missing_optional_data(self):
        def fake_health(entry, name, max_files):
            return {
                "dataset": name,
                "status": "ready" if name in {"admin_areas", "dem", "land_use"} else "unavailable",
                "kind": "vector" if name in {"admin_areas", "roads", "water"} else "raster",
                "file_count": 1 if name in {"admin_areas", "dem", "land_use"} else 0,
                "usable_for": ["example"] if name in {"admin_areas", "dem", "land_use"} else [],
                "checks": [],
                "metrics": {"checked_files": 1 if name in {"admin_areas", "dem", "land_use"} else 0},
            }

        with patch("domains.gis.adapters.data_quality._health_for_entry", side_effect=fake_health):
            report = dataset_health_report(DatasetCatalog("unused", {}))

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["core_status"], "ready")
        self.assertEqual(report["optional_status"], "unavailable")
        self.assertEqual(report["status_by_layer"]["optional"], "unavailable")
        self.assertTrue(all(item["layer"] == "core" for item in report["datasets"][:3]))
        self.assertTrue(all(item["layer"] == "optional" for item in report["datasets"][3:]))
        constrained = next(
            item for item in report["capability_catalog"]["capabilities"]
            if item["id"] == "constrained_buildability_screening"
        )
        self.assertEqual(constrained["capability_status"], "unavailable")
        self.assertFalse(constrained["available"])

    def test_capability_status_is_independent_for_core_and_optional_workflows(self):
        catalog = capability_catalog(
            environment="local",
            dataset_capabilities={
                "admin_areas": ["range_query"],
                "dem": ["get_raster_statistics"],
                "land_use": ["get_raster_statistics"],
            },
            dataset_statuses={
                "admin_areas": "ready",
                "dem": "degraded",
                "land_use": "ready",
                "roads": "unavailable",
                "water": "unavailable",
            },
        )
        raster = next(item for item in catalog["capabilities"] if item["id"] == "raster_metadata")
        vector = next(item for item in catalog["capabilities"] if item["id"] == "vector_summary")
        self.assertEqual(raster["capability_status"], "degraded")
        self.assertTrue(raster["available"])
        self.assertEqual(vector["capability_status"], "unavailable")
        self.assertFalse(vector["available"])
        self.assertEqual(raster["data_layer"], "core")
        self.assertEqual(vector["data_layer"], "mixed")

    def test_runtime_catalog_exposes_layer_health_and_per_capability_gate(self):
        snapshot = runtime_capability_catalog(
            {
                "status": "ready",
                "core_status": "ready",
                "optional_status": "unavailable",
                "updated_at": "2026-08-09T00:00:00Z",
                "datasets": [
                    {"dataset": "admin_areas", "status": "ready", "usable_for": ["range_query"]},
                    {"dataset": "dem", "status": "ready", "usable_for": ["get_raster_statistics"]},
                    {"dataset": "land_use", "status": "ready", "usable_for": ["get_raster_statistics"]},
                    {"dataset": "roads", "status": "unavailable", "usable_for": []},
                    {"dataset": "water", "status": "unavailable", "usable_for": []},
                ],
                "capabilities": {
                    "admin_areas": ["range_query"],
                    "dem": ["get_raster_statistics"],
                    "land_use": ["get_raster_statistics"],
                    "roads": [],
                    "water": [],
                },
            },
            environment="local",
        )
        self.assertEqual(snapshot["core_health_status"], "ready")
        self.assertEqual(snapshot["optional_health_status"], "unavailable")
        constrained = next(
            item for item in snapshot["capabilities"]
            if item["id"] == "constrained_buildability_screening"
        )
        self.assertFalse(constrained["available"])
        self.assertEqual(constrained["runtime_evidence"]["datasets"]["roads"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
