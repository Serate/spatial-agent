import unittest
from pathlib import Path

from tests.console_source import read_console_source
from unittest.mock import patch

from agent.capability_catalog import runtime_capability_catalog
from agent.service import AgentService


SOURCE_BINDING = {
    "binding_version": 1,
    "fingerprint": "sha256:abc123",
    "verification_mode": "sha256",
    "datasets": ["admin_areas", "dem", "land_use"],
    "status": "recorded",
}


class M73SourceBindingEvidenceTests(unittest.TestCase):
    def test_runtime_capability_copies_controlled_source_binding_to_data_evidence(self):
        health = {
            "status": "ready",
            "data_readiness": "ready",
            "datasets": [
                {"dataset": "dem", "status": "ready", "file_count": 1},
                {"dataset": "land_use", "status": "ready", "file_count": 1},
            ],
            "capabilities": {"dem": [], "land_use": []},
            "analysis_ready": {
                "status": "ready",
                "required": True,
                "derived_version": "analysis-ready-v1",
                "target_grid": {"crs": "EPSG:32649"},
                "grid_alignment": {"status": "aligned"},
                "source_binding": SOURCE_BINDING,
            },
        }
        snapshot = runtime_capability_catalog(health, environment="local")
        self.assertEqual(snapshot["analysis_ready"]["source_binding"], SOURCE_BINDING)
        self.assertEqual(snapshot["data_evidence"]["dem"]["analysis_ready"]["source_binding"], SOURCE_BINDING)

    def test_comparison_summary_preserves_source_binding(self):
        service = AgentService()
        evidence = {
            "status": "ready",
            "required": True,
            "derived_version": "analysis-ready-v1",
            "target_grid": {"crs": "EPSG:32649"},
            "grid_alignment": {"status": "aligned"},
            "source_binding": SOURCE_BINDING,
        }
        with patch("agent.application.comparisons._analysis_ready_summary", return_value=evidence):
            result = service.compare_buildability("洪山区", [20], backend="memory")
        self.assertEqual(result["analysis_ready"]["source_binding"]["fingerprint"], "sha256:abc123")

    def test_console_has_source_binding_marker(self):
        html = read_console_source(Path(__file__).parents[1])
        self.assertIn("analysisReadyBindingText", html)
        self.assertIn("源绑定 ", html)


if __name__ == "__main__":
    unittest.main()
