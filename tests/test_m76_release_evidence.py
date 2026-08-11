import unittest
from pathlib import Path
from unittest.mock import patch

from agent.capability_catalog import runtime_capability_catalog
from agent.service import AgentService


class M76ReleaseEvidenceTests(unittest.TestCase):
    def test_runtime_data_evidence_copies_output_manifest_summary(self):
        output_manifest = {
            "status": "ready",
            "verification_mode": "metadata",
            "hashes_verified": False,
            "verified_files": 0,
            "mismatch_count": 0,
            "outputs": {
                "dem": {
                    "reported": "dem_aligned.tif",
                    "manifest": ["dem_aligned.tif"],
                    "matched": True,
                }
            },
        }
        snapshot = runtime_capability_catalog(
            {
                "status": "ready",
                "data_readiness": "ready",
                "datasets": [{"dataset": "dem", "status": "ready", "file_count": 1}],
                "capabilities": {},
                "analysis_ready": {"status": "ready", "output_manifest": output_manifest},
            },
            environment="local",
        )
        self.assertEqual(snapshot["analysis_ready"]["output_manifest"], output_manifest)
        self.assertEqual(
            snapshot["data_evidence"]["dem"]["analysis_ready"]["output_manifest"],
            output_manifest,
        )

    def test_comparison_summary_keeps_bounded_output_matches(self):
        evidence = {
            "status": "ready",
            "output_manifest": {
                "status": "ready",
                "verification_mode": "metadata",
                "hashes_verified": False,
                "mismatch_count": 0,
                "outputs": {
                    "dem": {
                        "reported": "dem_aligned.tif",
                        "manifest": ["dem_aligned.tif"],
                        "matched": True,
                    }
                },
            },
        }
        with patch("agent.service._analysis_ready_summary", return_value=evidence):
            result = AgentService().compare_buildability("洪山区", [20], backend="memory")
        self.assertTrue(result["analysis_ready"]["output_manifest"]["outputs"]["dem"]["matched"])

    def test_console_and_browser_smoke_cover_three_release_evidence_layers(self):
        root = Path(__file__).parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        smoke = (root / "scripts" / "console_overview_smoke.js").read_text(encoding="utf-8")
        for marker in (
            "releaseEvidence",
            "发布完整性",
            "元数据与网格",
            "源绑定 SHA-256",
            "输出 manifest",
            "verificationModeLabel",
        ):
            self.assertIn(marker, html)
        for marker in ("发布完整性", "源绑定 SHA-256", "输出 manifest", "dem_aligned.tif"):
            self.assertIn(marker, smoke)


if __name__ == "__main__":
    unittest.main()
