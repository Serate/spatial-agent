import json
import tempfile
import unittest
from pathlib import Path

from agent.data_quality import dataset_health_report
from agent.dataset_catalog import DatasetCatalog, DatasetEntry
from agent.dataset_manifest import build_dataset_manifest, verify_dataset_manifest
from scripts.bind_dataset_manifest import bind_manifest


class M69DatasetManifestTests(unittest.TestCase):
    def _catalog(self, root):
        return DatasetCatalog(
            str(root),
            {
                "roads": DatasetEntry(
                    "roads", "vector", "geojson", "roads", [str(root / "roads.geojson")],
                    source="OSM", version="2026", attribution="© OSM", license="ODbL 1.0",
                ),
            },
        )

    def test_manifest_is_deterministic_and_contains_hash_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "roads.geojson").write_text('{"type":"FeatureCollection"}\n', encoding="utf-8")
            manifest = build_dataset_manifest(self._catalog(root))
            self.assertEqual(manifest["manifest_version"], 1)
            file_info = manifest["datasets"]["roads"]["files"][0]
            self.assertEqual(file_info["path"], "roads.geojson")
            self.assertEqual(len(file_info["sha256"]), 64)
            self.assertEqual(manifest, build_dataset_manifest(self._catalog(root)))

    def test_manifest_verification_detects_mutation_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "roads.geojson"
            path.write_text("one", encoding="utf-8")
            catalog = self._catalog(root)
            manifest = build_dataset_manifest(catalog)
            self.assertEqual(verify_dataset_manifest(catalog, manifest)["status"], "ready")
            path.write_text("changed", encoding="utf-8")
            result = verify_dataset_manifest(catalog, manifest)
            self.assertEqual(result["status"], "degraded")
            self.assertTrue(any("sha256" in item for item in result["mismatches"]))
            self.assertEqual(result["verification_mode"], "sha256")
            self.assertFalse(result["metadata_only"])

    def test_full_verification_requires_hashes_in_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "roads.geojson").write_text("one", encoding="utf-8")
            manifest = build_dataset_manifest(self._catalog(root))
            del manifest["datasets"]["roads"]["files"][0]["sha256"]
            result = verify_dataset_manifest(self._catalog(root), manifest)
            self.assertEqual(result["status"], "degraded")
            self.assertEqual(result["verification_mode"], "sha256")
            self.assertFalse(result["hashes_verified"])
            self.assertTrue(any("missing or invalid" in item for item in result["mismatches"]))

    def test_health_report_uses_manifest_as_an_explicit_lightweight_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "roads.geojson"
            path.write_text("one", encoding="utf-8")
            catalog = self._catalog(root)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(build_dataset_manifest(catalog)), encoding="utf-8")
            catalog.manifest_path = str(manifest_path)
            report = dataset_health_report(catalog, dataset="roads", max_files=1)
            self.assertEqual(report["manifest"]["status"], "ready")
            self.assertFalse(report["manifest"]["hashes_verified"])
            self.assertEqual(report["manifest"]["verification_mode"], "metadata")
            self.assertEqual(report["data_readiness"], "ready")

    def test_required_manifest_is_visible_as_not_ready_when_missing(self):
        catalog = DatasetCatalog("unused", {}, manifest_required=True)
        report = dataset_health_report(catalog, dataset="roads", max_files=1)
        self.assertEqual(report["data_readiness"], "not_ready")

    def test_bind_manifest_creates_required_relative_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "template.json"
            manifest = root / "data" / "manifest.json"
            output = root / "local" / "datasets.json"
            manifest.parent.mkdir()
            manifest.write_text("{}", encoding="utf-8")
            template.write_text(json.dumps({"root": "D:/data", "datasets": {}}), encoding="utf-8")
            bind_manifest(str(template), str(manifest), str(output))
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(payload["manifest_required"])
            self.assertEqual(payload["manifest"], "../data/manifest.json")
            catalog = DatasetCatalog.from_json(str(output))
            self.assertTrue(catalog.manifest_required)
            self.assertEqual(Path(catalog.manifest_path).resolve(), manifest.resolve())


if __name__ == "__main__":
    unittest.main()
