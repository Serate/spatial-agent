import unittest

from agent.capability_catalog import runtime_capability_catalog
from domains.gis.adapters.data_quality import _analysis_output_manifest_summary
from agent.service import AgentService
from unittest.mock import patch


class M75OutputManifestEvidenceTests(unittest.TestCase):
    def test_output_manifest_matches_reported_derived_files(self):
        result = _analysis_output_manifest_summary(
            {"outputs": {"dem": "dem_aligned.tif", "land_use": "land_use_aligned.tif"}},
            {
                "status": "ready",
                "verification_mode": "metadata",
                "hashes_verified": False,
                "verified_files": 5,
                "datasets": {
                    "dem": {"files": [{"path": "../../analysis-ready/dem_aligned.tif"}]},
                    "land_use": {"files": [{"path": "../../analysis-ready/land_use_aligned.tif"}]},
                },
            },
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["mismatch_count"], 0)
        self.assertFalse(result["hashes_verified"])

    def test_output_manifest_mismatch_is_explicit(self):
        result = _analysis_output_manifest_summary(
            {"outputs": {"dem": "dem_aligned.tif", "land_use": "land_use_aligned.tif"}},
            {
                "status": "ready",
                "datasets": {
                    "dem": {"files": [{"path": "dem_other.tif"}]},
                    "land_use": {"files": [{"path": "land_use_aligned.tif"}]},
                },
            },
        )
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["mismatch_count"], 1)

    def test_health_manifest_basename_summary_is_enough_for_matching(self):
        result = _analysis_output_manifest_summary(
            {"outputs": {"dem": "dem_aligned.tif", "land_use": "land_use_aligned.tif"}},
            {
                "status": "ready",
                "verification_mode": "metadata",
                "dataset_file_names": {
                    "dem": ["dem_aligned.tif"],
                    "land_use": ["land_use_aligned.tif"],
                },
            },
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["mismatch_count"], 0)

    def test_capability_and_comparison_keep_output_manifest_layer(self):
        output_manifest = {
            "status": "ready",
            "verification_mode": "metadata",
            "hashes_verified": False,
            "verified_files": 5,
            "mismatch_count": 0,
        }
        health = {
            "status": "ready",
            "data_readiness": "ready",
            "datasets": [],
            "capabilities": {},
            "analysis_ready": {
                "status": "ready",
                "source_binding": {"fingerprint": "sha256:x", "datasets": []},
                "output_manifest": output_manifest,
            },
        }
        snapshot = runtime_capability_catalog(health, environment="local")
        self.assertEqual(snapshot["analysis_ready"]["output_manifest"], output_manifest)
        service = AgentService()
        evidence = {"status": "ready", "output_manifest": output_manifest}
        with patch("agent.service._analysis_ready_summary", return_value=evidence):
            result = service.compare_buildability("洪山区", [20], backend="memory")
        self.assertEqual(result["analysis_ready"]["output_manifest"], output_manifest)


if __name__ == "__main__":
    unittest.main()
