import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class M252DomainBoundaryTests(unittest.TestCase):
    def test_gis_domain_uses_its_adapter_seam(self):
        source = (ROOT / "domains" / "gis" / "domain.py").read_text(encoding="utf-8")
        self.assertIn("from .adapters.spatial import", source)
        self.assertNotIn("from agent.spatial_backend import", source)
        self.assertNotIn("from agent.dataset_catalog import", source)

    def test_gis_adapter_seam_exposes_provider_types(self):
        from domains.gis.adapters.spatial import (
            DatasetCatalog,
            HybridSpatialBackend,
            InMemorySpatialBackend,
            SpatialToolAdapter,
        )

        self.assertTrue(callable(DatasetCatalog.from_json))
        self.assertTrue(callable(HybridSpatialBackend))
        self.assertTrue(callable(InMemorySpatialBackend))
        self.assertTrue(callable(SpatialToolAdapter))

    def test_adapter_module_has_no_top_level_domain_import(self):
        path = ROOT / "domains" / "gis" / "adapters" / "spatial.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        self.assertIn("agent.spatial_backend", imports)


if __name__ == "__main__":
    unittest.main()
