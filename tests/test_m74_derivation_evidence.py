import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from domains.gis.adapters.data_quality import dataset_health_report
from domains.gis.adapters.dataset_catalog import DatasetCatalog, DatasetEntry


class M74DerivationEvidenceTests(unittest.TestCase):
    def _catalog(self, report_path):
        entries = {
            name: DatasetEntry(
                name,
                "raster" if name in {"dem", "land_use"} else "vector",
                "tif",
                name,
                [f"{name}.tif"],
            )
            for name in ("admin_areas", "dem", "land_use", "roads", "water")
        }
        return DatasetCatalog(
            "unused",
            entries,
            analysis_ready_report_path=str(report_path),
            analysis_ready_required=True,
        )

    def _report(self):
        return {
            "derived_version": "analysis-ready-v1",
            "target_grid": {
                "crs": "EPSG:32649",
                "resolution": [30, 30],
                "bounds": [0, 0, 60, 60],
                "width": 2,
                "height": 2,
            },
            "grid_alignment": {"status": "aligned"},
            "outputs": {"dem": "dem.tif", "land_use": "land_use.tif"},
            "derivation": {
                "resampling": {"dem": "bilinear", "land_use": "nearest"},
                "nodata": {"dem": -9999.0, "land_use": 0},
                "boundary": {
                    "scope": "test boundary",
                    "source_crs": "EPSG:4490",
                    "district_count": 13,
                },
            },
        }

    def _health_patches(self):
        metadata = {
            "crs": "EPSG:32649",
            "bounds": [0, 0, 60, 60],
            "width": 2,
            "height": 2,
            "pixel_size": [30, 30],
            "transform": [30, 0, 0, 0, -30, 60],
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

        return (
            patch("domains.gis.adapters.data_quality._health_for_entry", side_effect=fake_health),
            patch("domains.gis.adapters.data_quality._raster_alignment_summary", return_value={"status": "ready"}),
        )

    def test_valid_derivation_evidence_is_exposed(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            report_path.write_text(json.dumps(self._report()), encoding="utf-8")
            patches = self._health_patches()
            with patches[0], patches[1]:
                result = dataset_health_report(self._catalog(report_path))
        self.assertEqual(result["data_readiness"], "ready")
        self.assertEqual(result["analysis_ready"]["derivation"]["resampling"]["land_use"], "nearest")
        self.assertEqual(result["analysis_ready"]["derivation"]["boundary"]["district_count"], 13)

    def test_invalid_resampling_blocks_required_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            report = self._report()
            report["derivation"]["resampling"]["land_use"] = "bilinear"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            patches = self._health_patches()
            with patches[0], patches[1]:
                result = dataset_health_report(self._catalog(report_path))
        self.assertEqual(result["analysis_ready"]["status"], "degraded")
        self.assertEqual(result["data_readiness"], "not_ready")
        self.assertTrue(any("nearest" in item for item in result["analysis_ready"]["errors"]))


if __name__ == "__main__":
    unittest.main()
