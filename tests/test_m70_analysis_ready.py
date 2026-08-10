import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.answer_composer import AnswerComposer
from agent.capability_catalog import runtime_capability_catalog
from agent.data_quality import dataset_health_report
from agent.dataset_catalog import DatasetCatalog, DatasetEntry
from agent.models import AgentRunResult, RunStatus, StepRun, TaskPlan
from scripts.prepare_analysis_rasters import _write_analysis_config, _warp_sources


try:
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject

    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False


@unittest.skipUnless(HAS_RASTERIO, "requires rasterio")
class M70AnalysisReadyRasterTests(unittest.TestCase):
    def _write_source(self, path, values, *, dtype, nodata):
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=len(values),
            width=len(values[0]),
            count=1,
            dtype=dtype,
            crs="EPSG:32649",
            transform=from_origin(0, 60, 30, 30),
            nodata=nodata,
        ) as destination:
            destination.write(values, 1)

    def test_warp_outputs_share_the_explicit_target_grid(self):
        import numpy

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dem_source = root / "dem.tif"
            land_source = root / "land.tif"
            self._write_source(
                dem_source,
                numpy.array([[10, 11], [12, 13]], dtype="float32"),
                dtype="float32",
                nodata=-9999.0,
            )
            self._write_source(
                land_source,
                numpy.array([[10, 20], [30, 40]], dtype="uint16"),
                dtype="uint16",
                nodata=0,
            )
            target_transform = from_origin(0, 60, 30, 30)
            dem_output = root / "dem_aligned.tif"
            land_output = root / "land_aligned.tif"
            common = {
                "target_crs": "EPSG:32649",
                "transform": target_transform,
                "width": 2,
                "height": 2,
                "rasterio": rasterio,
                "numpy": numpy,
                "reproject": reproject,
            }
            _warp_sources(
                [str(dem_source)],
                dem_output,
                **common,
                dtype="float32",
                nodata=-9999.0,
                resampling=Resampling.bilinear,
            )
            _warp_sources(
                [str(land_source)],
                land_output,
                **common,
                dtype="uint16",
                nodata=0,
                resampling=Resampling.nearest,
            )
            with rasterio.open(dem_output) as dem, rasterio.open(land_output) as land:
                self.assertEqual(str(dem.crs), str(land.crs))
                self.assertEqual((dem.width, dem.height), (land.width, land.height))
                self.assertEqual(tuple(dem.transform), tuple(land.transform))
                self.assertEqual(dem.nodata, -9999.0)
                self.assertEqual(land.nodata, 0)

    def test_derived_config_replaces_source_raster_globs_without_losing_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            target = root / "derived.json"
            output_dir = root / "analysis-ready"
            source.write_text(
                json.dumps(
                    {
                        "root": "D:/data",
                        "datasets": {
                            "dem": {
                                "kind": "raster",
                                "format": "img",
                                "glob": "dem/*.img",
                                "role": "elevation",
                                "source": "ASTER",
                                "version": "v3",
                            },
                            "land_use": {
                                "kind": "raster",
                                "format": "tif",
                                "glob": "land/*.tif",
                                "role": "land use",
                                "source": "source",
                                "version": "2025",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            _write_analysis_config(source, target, output_dir)
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(payload["datasets"]["dem"]["path"], str((output_dir / "dem_aligned.tif").resolve()))
            self.assertNotIn("glob", payload["datasets"]["dem"])
            self.assertEqual(payload["datasets"]["dem"]["version"], "v3-analysis-ready")
            self.assertEqual(payload["datasets"]["land_use"]["source"], "Spatial Agent reproducible aligned derivative")
            self.assertEqual(payload["analysis_ready"]["report"], "analysis-ready/analysis-ready-report.json")
            self.assertTrue(payload["analysis_ready"]["required"])

    def _catalog(self, report_path, *, report_required=True):
        entries = {
            name: DatasetEntry(
                name,
                "vector" if name in {"admin_areas", "roads", "water"} else "raster",
                "geojson" if name == "admin_areas" else "tif",
                name,
                [
                    "dem_aligned.tif" if name == "dem" else
                    "land_use_aligned.tif" if name == "land_use" else
                    f"{name}.tif"
                ],
            )
            for name in ("admin_areas", "dem", "land_use", "roads", "water")
        }
        return DatasetCatalog(
            "unused",
            entries,
            analysis_ready_report_path=str(report_path),
            analysis_ready_required=report_required,
        )

    def _report(self, dem_name="dem_aligned.tif", land_name="land_use_aligned.tif"):
        return {
            "report_version": "1",
            "derived_version": "analysis-ready-v1",
            "target_grid": {
                "crs": "EPSG:32649",
                "resolution": [30, 30],
                "bounds": [0, 0, 60, 60],
                "width": 2,
                "height": 2,
            },
            "grid_alignment": {
                "status": "aligned",
                "metadata_only": True,
                "pixels_read": False,
            },
            "outputs": {"dem": dem_name, "land_use": land_name},
            "evidence": {"boundary_scope": "test", "pixels_read": False},
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
                "usable_for": ["get_dataset_schema"],
                "checks": [],
                "metrics": {"checked_files": 1},
            }

        return patch("agent.data_quality._health_for_entry", side_effect=fake_health), patch(
            "agent.data_quality._raster_alignment_summary",
            return_value={"status": "ready", "overlapping_pairs": 1},
        )

    def test_valid_analysis_ready_report_is_exposed_and_required(self):
        import json

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "analysis-ready-report.json"
            report.write_text(json.dumps(self._report()), encoding="utf-8")
            catalog = self._catalog(report)
            patches = self._health_patches()
            with patches[0], patches[1]:
                result = dataset_health_report(catalog)

        evidence = result["analysis_ready"]
        self.assertEqual(evidence["status"], "ready")
        self.assertEqual(evidence["derived_version"], "analysis-ready-v1")
        self.assertEqual(evidence["target_grid"]["crs"], "EPSG:32649")
        self.assertEqual(evidence["target_grid"]["width"], 2)
        self.assertEqual(result["data_readiness"], "ready")
        self.assertIn("get_zonal_buildability_analysis", result["capabilities"]["dem"])
        buildability = next(
            item for item in result["capability_catalog"]["capabilities"]
            if item["id"] == "buildability_screening"
        )
        self.assertTrue(buildability["available"])

    def test_missing_required_report_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = self._catalog(Path(directory) / "missing.json")
            patches = self._health_patches()
            with patches[0], patches[1]:
                result = dataset_health_report(catalog)

        self.assertEqual(result["analysis_ready"]["status"], "unavailable")
        self.assertEqual(result["data_readiness"], "not_ready")
        self.assertNotIn("get_zonal_buildability_analysis", result["capabilities"]["dem"])
        buildability = next(
            item for item in result["capability_catalog"]["capabilities"]
            if item["id"] == "buildability_screening"
        )
        self.assertFalse(buildability["available"])

    def test_report_output_mismatch_blocks_required_readiness(self):
        import json

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "analysis-ready-report.json"
            report.write_text(json.dumps(self._report(dem_name="other.tif")), encoding="utf-8")
            catalog = self._catalog(report)
            patches = self._health_patches()
            with patches[0], patches[1]:
                result = dataset_health_report(catalog)

        self.assertEqual(result["analysis_ready"]["status"], "degraded")
        self.assertEqual(result["data_readiness"], "not_ready")
        self.assertIn("dem", " ".join(result["analysis_ready"]["errors"]).lower())

    def test_invalid_target_grid_values_block_required_readiness(self):
        import json

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "analysis-ready-report.json"
            payload = self._report()
            payload["target_grid"]["width"] = 0
            payload["target_grid"]["resolution"] = [0, 30]
            report.write_text(json.dumps(payload), encoding="utf-8")
            catalog = self._catalog(report)
            patches = self._health_patches()
            with patches[0], patches[1]:
                result = dataset_health_report(catalog)

        self.assertEqual(result["analysis_ready"]["status"], "degraded")
        self.assertEqual(result["data_readiness"], "not_ready")
        self.assertTrue(any("分辨率" in item for item in result["analysis_ready"]["errors"]))

    def test_runtime_capability_and_answer_expose_derived_grid_evidence(self):
        health = {
            "status": "ready",
            "data_readiness": "ready",
            "datasets": [
                {"dataset": "dem", "status": "ready", "file_count": 1, "crs_values": ["EPSG:32649"]},
                {"dataset": "land_use", "status": "ready", "file_count": 1, "crs_values": ["EPSG:32649"]},
            ],
            "capabilities": {"dem": [], "land_use": []},
            "analysis_ready": {"status": "ready", "required": True, **self._report()},
        }
        snapshot = runtime_capability_catalog(health, environment="local")
        self.assertEqual(snapshot["analysis_ready"]["derived_version"], "analysis-ready-v1")
        self.assertEqual(snapshot["data_evidence"]["dem"]["analysis_ready"]["status"], "ready")

        result = AgentRunResult(
            run_id="analysis-ready-answer",
            status=RunStatus.COMPLETED,
            request="检查数据健康",
            plan=TaskPlan(goal="health", steps=[], output={"type": "dataset_health_result"}),
            steps=[StepRun(id="health", tool="get_dataset_health_report", args={}, status="COMPLETED", result=health)],
        )
        answer = AnswerComposer().compose(result)
        self.assertIn("analysis-ready-v1", answer)
        self.assertIn("EPSG:32649", answer)


if __name__ == "__main__":
    unittest.main()
