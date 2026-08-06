import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_truncates_geometry_summary_to_size_limit(self):
        path = export_run_summary(
            {"run_id": "run-1", "steps": []},
            root=tempfile.gettempdir(),
            max_bytes=2000,
            geometry_features=[
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [[[float(i), 0], [float(i), 1], [float(i + 1), 1], [float(i + 1), 0], [float(i), 0]] for i in range(500)]},
                    "properties": {},
                }
            ],
        )
        payload = json.loads(Path(path).read_text(encoding="utf-8"))

        self.assertTrue(payload["properties"]["geometry_truncated"])

    def test_service_returns_geojson_ref(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AgentService()
            result = service.run("查询DEM栅格元数据")
            ref = export_run_summary(result, root=tmpdir)

        self.assertTrue(ref.endswith(".geojson"))

    def test_service_export_geojson_uses_runtime_result_export(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            def write_to_temp(payload, geometry_features=None):
                return export_run_summary(
                    payload, root=tmpdir, geometry_features=geometry_features
                )

            with patch("agent.service.export_run_summary", side_effect=write_to_temp):
                result = AgentService().run(
                    "查询DEM栅格元数据", export_geojson=True
                )
            document = json.loads(Path(result["geojson_ref"]).read_text(encoding="utf-8"))

        self.assertEqual(document["type"], "FeatureCollection")
        self.assertEqual(len(document["features"]), 1)
        self.assertIsNone(document["features"][0]["geometry"])


if __name__ == "__main__":
    unittest.main()
