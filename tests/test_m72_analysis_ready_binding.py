import tempfile
import unittest
from pathlib import Path

from agent.analysis_ready_binding import build_source_binding, verify_source_binding
from domains.gis.adapters.dataset_catalog import DatasetCatalog, DatasetEntry


class M72AnalysisReadyBindingTests(unittest.TestCase):
    def _catalog(self, root):
        return DatasetCatalog(
            str(root),
            {
                name: DatasetEntry(
                    name,
                    "raster" if name in {"dem", "land_use"} else "vector",
                    "tif" if name in {"dem", "land_use"} else "geojson",
                    name,
                    [str(root / (name + ".data"))],
                    source="test-source",
                    version="v1",
                )
                for name in ("admin_areas", "dem", "land_use")
            },
        )

    def test_source_binding_is_deterministic_and_verifiable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("admin_areas", "dem", "land_use"):
                (root / (name + ".data")).write_bytes(name.encode("ascii"))
            catalog = self._catalog(root)
            binding = build_source_binding(catalog)
            self.assertTrue(binding["fingerprint"].startswith("sha256:"))
            result = verify_source_binding(catalog, binding)
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["verified_files"], 3)

    def test_source_mutation_is_reported_before_reusing_derivation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("admin_areas", "dem", "land_use"):
                (root / (name + ".data")).write_bytes(name.encode("ascii"))
            catalog = self._catalog(root)
            binding = build_source_binding(catalog)
            (root / "dem.data").write_bytes(b"changed")
            result = verify_source_binding(catalog, binding)
            self.assertEqual(result["status"], "degraded")
            self.assertIn("source datasets changed since derivation", result["mismatches"])
            self.assertFalse(result["hashes_verified"])

    def test_malformed_binding_is_a_controlled_unavailable_result(self):
        with tempfile.TemporaryDirectory() as directory:
            result = verify_source_binding(self._catalog(Path(directory)), {"datasets": []})
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["mismatch_count"], 1)


if __name__ == "__main__":
    unittest.main()
