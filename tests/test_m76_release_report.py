import json
import tempfile
import unittest
from pathlib import Path

from tests.console_source import read_console_source
from unittest.mock import patch

from agent.analysis_ready_binding import build_source_binding
from agent.dataset_catalog import DatasetCatalog, DatasetEntry
from agent.dataset_manifest import build_dataset_manifest
from agent.release_evidence import release_evidence_snapshot


class M76ReleaseReportTests(unittest.TestCase):
    def _entries(self, root=None):
        return {
            name: DatasetEntry(
                name,
                "raster" if name in {"dem", "land_use"} else "vector",
                "tif",
                name,
                [
                    str(
                        (root or Path("."))
                        / (name + ("_aligned.tif" if name in {"dem", "land_use"} else ".geojson"))
                    )
                ],
                source="test-source",
                version="v1",
            )
            for name in ("admin_areas", "dem", "land_use")
        }

    def _health_patch(self):
        def fake_health(entry, name, max_files):
            return {
                "dataset": name,
                "status": "ready",
                "kind": entry.kind if entry else None,
                "file_count": len(entry.files) if entry else 0,
                "crs_values": ["EPSG:32649"] if entry and entry.kind == "raster" else [],
                "bounds": [0, 0, 60, 60],
                "checks": [],
                "metrics": {"checked_files": len(entry.files) if entry else 0},
                "usable_for": [],
            }

        return patch("agent.data_quality._health_for_entry", side_effect=fake_health)

    def test_full_report_separates_metadata_source_and_output_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entries = self._entries(root)
            for name, entry in entries.items():
                path = root / Path(entry.files[0]).name
                path.write_bytes(name.encode("ascii"))
            catalog = DatasetCatalog(str(root), entries)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(build_dataset_manifest(catalog), ensure_ascii=True),
                encoding="utf-8",
            )
            report_path = root / "analysis-ready-report.json"
            report = {
                "derived_version": "analysis-ready-v1",
                "target_grid": {
                    "crs": "EPSG:32649",
                    "resolution": [30, 30],
                    "bounds": [0, 0, 60, 60],
                    "width": 2,
                    "height": 2,
                },
                "grid_alignment": {"status": "aligned"},
                "outputs": {"dem": "dem_aligned.tif", "land_use": "land_use_aligned.tif"},
                "source_binding": build_source_binding(catalog),
            }
            report_path.write_text(json.dumps(report), encoding="utf-8")
            config_path = root / "datasets.json"
            config_path.write_text(
                json.dumps(
                    {
                        "root": str(root),
                        "datasets": {
                            name: {
                                "kind": entry.kind,
                                "format": entry.format,
                                "role": entry.role,
                                "path": Path(entry.files[0]).name,
                                "source": entry.source,
                                "version": entry.version,
                            }
                            for name, entry in entries.items()
                        },
                        "manifest": {"path": manifest_path.name, "required": True},
                        "analysis_ready": {"report": report_path.name, "required": True},
                    }
                ),
                encoding="utf-8",
            )
            with self._health_patch(), patch(
                "agent.data_quality._raster_alignment_summary",
                return_value={"status": "aligned"},
            ):
                result = release_evidence_snapshot(str(config_path))
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["metadata"]["data_readiness"], "ready")
        self.assertEqual(result["source_binding"]["status"], "ready")
        self.assertTrue(result["source_binding"]["hashes_verified"])
        self.assertEqual(result["output_manifest"]["status"], "ready")
        self.assertTrue(result["output_manifest"]["hashes_verified"])
        self.assertEqual(result["output_manifest"]["verified_files"], 2)

    def test_missing_config_is_a_bounded_unavailable_report(self):
        result = release_evidence_snapshot("D:/path-that-does-not-exist/datasets.json")
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("D:/path-that-does-not-exist", json.dumps(result))

    def test_release_report_is_exposed_by_both_http_entrypoints_and_console(self):
        from pathlib import Path
        from tests.console_source import read_console_source

        root = Path(__file__).parents[1]
        serve = (root / "serve_api.py").read_text(encoding="utf-8")
        production = (root / "production_api.py").read_text(encoding="utf-8")
        console = read_console_source(root)
        for source in (serve, production, console):
            self.assertIn("release-evidence", source)


if __name__ == "__main__":
    unittest.main()
