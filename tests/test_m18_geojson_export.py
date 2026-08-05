import json
import tempfile
import unittest
from pathlib import Path

from agent.geojson_exporter import export_run_summary
from agent.service import AgentService


class M18GeoJSONExportTests(unittest.TestCase):
    def test_exports_bounded_summary_features_without_args(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_run_summary(
                {
                    "run_id": "run-1",
                    "status": "COMPLETED",
                    "steps": [
                        {
                            "id": "raster",
                            "tool": "get_raster_metadata",
                            "args": {"dataset": "dem"},
                            "status": "COMPLETED",
                            "latency_ms": 2.5,
                            "result": {"file_count": 9, "result_ref": "local://raster"},
                        }
                    ],
                },
                root=tmpdir,
            )
            payload = json.loads(Path(path).read_text(encoding="utf-8"))

        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertIsNone(payload["features"][0]["geometry"])
        self.assertNotIn("args", payload["features"][0]["properties"])
        self.assertEqual(payload["features"][0]["properties"]["file_count"], 9)

    def test_rejects_summary_over_size_limit(self):
        with self.assertRaises(ValueError):
            export_run_summary(
                {"run_id": "run-1", "steps": [{"error": "x" * 1000}]},
                root=tempfile.gettempdir(),
                max_bytes=10,
            )

    def test_service_returns_geojson_ref(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AgentService()
            result = service.run("查询DEM栅格元数据")
            ref = export_run_summary(result, root=tmpdir)

        self.assertTrue(ref.endswith(".geojson"))


if __name__ == "__main__":
    unittest.main()
