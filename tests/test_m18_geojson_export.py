import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.geojson_exporter import (
    DEFAULT_GEOJSON_MAX_FEATURES,
    DEFAULT_MAX_BYTES,
    GEOJSON_MAX_BYTES_ENV,
    HARD_MAX_BYTES,
    export_run_summary,
    resolve_max_bytes,
)
from agent.geometry_export import normalize_feature_collection
from agent.service import AgentService, _exported_geometry_evidence, _tag_geometry_features


class M18GeoJSONExportTests(unittest.TestCase):
    def test_default_export_budget_supports_tens_of_megabytes(self):
        self.assertGreaterEqual(DEFAULT_MAX_BYTES, 50 * 1024 * 1024)
        self.assertGreater(DEFAULT_MAX_BYTES, 100_000)
        self.assertEqual(DEFAULT_GEOJSON_MAX_FEATURES, 10_000)
        self.assertLessEqual(resolve_max_bytes(), HARD_MAX_BYTES)

    def test_export_budget_is_configurable_but_hard_bounded(self):
        with patch.dict("os.environ", {GEOJSON_MAX_BYTES_ENV: str(75 * 1024 * 1024)}, clear=False):
            self.assertEqual(resolve_max_bytes(), 75 * 1024 * 1024)
        with patch.dict("os.environ", {GEOJSON_MAX_BYTES_ENV: str(250 * 1024 * 1024)}, clear=False):
            self.assertEqual(resolve_max_bytes(), HARD_MAX_BYTES)

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

    def test_export_preserves_result_type_for_dynamic_map_rendering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_run_summary(
                {"run_id": "overview-run", "status": "COMPLETED", "result_type": "spatial_overview_result", "steps": []},
                root=tmpdir,
            )
            payload = json.loads(Path(path).read_text(encoding="utf-8"))

        self.assertEqual(payload["properties"]["result_type"], "spatial_overview_result")

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

    def test_merged_geometry_features_keep_source_and_crs(self):
        tagged = _tag_geometry_features(
            [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {"kind": "candidate"}}],
            source="raster-buildability-screening",
            crs={"type": "name", "properties": {"name": "EPSG:32650"}},
        )

        self.assertEqual(tagged[0]["properties"]["geometry_source"], "raster-buildability-screening")
        self.assertEqual(tagged[0]["properties"]["geometry_crs"], "EPSG:32650")

    def test_merged_geometry_features_keep_dataset_label(self):
        tagged = _tag_geometry_features(
            [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}, "properties": {}}],
            source="geopackage",
            dataset="roads",
        )
        self.assertEqual(tagged[0]["properties"]["dataset"], "roads")

    def test_exported_geometry_evidence_measures_truncated_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_run_summary(
                {"run_id": "truncated-run", "status": "COMPLETED", "steps": []},
                root=tmpdir,
                max_bytes=2000,
                geometry_features=[
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [[[float(i), 0], [float(i), 1], [float(i + 1), 1], [float(i + 1), 0], [float(i), 0]] for i in range(500)]},
                        "properties": {"geometry_source": "geopackage", "dataset": "roads"},
                    }
                ],
            )
            count, evidence = _exported_geometry_evidence(path)

        self.assertEqual(count, 0)
        self.assertEqual(evidence["status"], "truncated_geometry")
        self.assertTrue(evidence["truncated"])

    def test_map_export_records_display_and_source_crs(self):
        with patch("agent.geometry_export._transform_geometry", return_value={"type": "Point", "coordinates": [114.4, 30.5]}):
            document = normalize_feature_collection({
                "type": "FeatureCollection",
                "crs": {"type": "name", "properties": {"name": "EPSG:32650"}},
                "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [500000, 3300000]}, "properties": {}}],
            })

        self.assertEqual(document["crs"]["properties"]["name"], "EPSG:4326")
        self.assertEqual(document["features"][0]["properties"]["geometry_source_crs"], "EPSG:32650")


if __name__ == "__main__":
    unittest.main()
