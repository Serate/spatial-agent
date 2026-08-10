import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from agent.data_quality import dataset_health_report
from agent.dataset_catalog import DatasetCatalog, DatasetEntry
from agent.runtime_capabilities import runtime_capability_snapshot
from agent.workflow_templates import workflow_template_catalog
from serve_api import AgentApiHandler


class M68IntegrationTests(unittest.TestCase):
    def test_health_report_exposes_metadata_only_grid_alignment(self):
        metadata = {
            "crs": "EPSG:32650",
            "bounds": [0, 0, 100, 100],
            "width": 100,
            "height": 100,
            "pixel_size": [1, 1],
            "transform": [1, 0, 0, 0, -1, 100],
        }

        def fake_health(entry, name, max_files):
            return {
                "dataset": name,
                "status": "ready",
                "kind": entry.kind if entry else None,
                "file_count": 1,
                "metadata_samples": [metadata] if name in {"dem", "land_use"} else [],
                "usable_for": [],
                "checks": [],
                "metrics": {"checked_files": 1},
            }

        catalog = DatasetCatalog(
            "unused",
            {
                "dem": DatasetEntry("dem", "raster", "tif", "dem", ["dem.tif"]),
                "land_use": DatasetEntry(
                    "land_use", "raster", "tif", "land use", ["land.tif"]
                ),
            },
        )
        with patch("agent.data_quality._health_for_entry", side_effect=fake_health):
            report = dataset_health_report(catalog)

        alignment = report["relationships"]["dem_land_use"]["grid_alignment"]
        self.assertEqual(alignment["status"], "aligned")
        self.assertTrue(alignment["metadata_only"])
        self.assertFalse(alignment["pixels_read"])

    def test_runtime_snapshot_propagates_alignment_relationships(self):
        health = {
            "status": "ready",
            "core_status": "ready",
            "optional_status": "unavailable",
            "datasets": [],
            "capabilities": {},
            "relationships": {
                "dem_land_use": {"grid_alignment": {"status": "grid_mismatch"}}
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "datasets.json"
            config.write_text('{"root":"' + directory.replace("\\", "/") + '","datasets":{}}', encoding="utf-8")
            with patch.dict("os.environ", {"SPATIAL_AGENT_DATASET_CONFIG": str(config)}), patch(
                "agent.runtime_capabilities.dataset_health_report", return_value=health
            ), patch(
                "agent.runtime_capabilities.environment_status",
                return_value={
                    "capabilities": {"local_gis_backend": False},
                    "dependencies": {"geopandas": False, "rasterio": False},
                },
            ):
                snapshot = runtime_capability_snapshot(max_files=1)

        self.assertEqual(
            snapshot["relationships"]["dem_land_use"]["grid_alignment"]["status"],
            "grid_mismatch",
        )

    def test_workflows_endpoint_returns_controlled_templates(self):
        class TestHandler(AgentApiHandler):
            service = AgentApiHandler.service

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            connection.request("GET", "/workflows")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(response.status, 200)
        self.assertIn("spatial_overview", body)
        self.assertEqual(set(workflow_template_catalog()), set(__import__("json").loads(body)["templates"]))


if __name__ == "__main__":
    unittest.main()
