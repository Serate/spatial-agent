import json
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService


class M35ProvenanceTests(unittest.TestCase):
    def test_service_returns_safe_step_lineage(self):
        result = AgentService().run(
            "查询洪山区行政区边界并分析DEM高程概况",
            export_artifact=False,
        )

        self.assertIn("provenance", result)
        entries = result["provenance"]["steps"]
        self.assertEqual(entries[2]["id"], "filter-admin")
        self.assertEqual(entries[3]["depends_on"], ["filter-admin"])
        self.assertEqual(
            entries[3]["input_bindings"],
            [{"source_step": "filter-admin", "path": "first_name"}],
        )
        self.assertNotIn("args", result["provenance"])
        self.assertNotIn("api_key", json.dumps(result["provenance"]))

    def test_artifact_persists_provenance_without_raw_step_args(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = AgentService(
                artifact_store=ArtifactStore(tmpdir)
            ).run(
                "查询洪山区行政区边界并分析DEM高程概况",
                export_artifact=True,
            )
            artifact = json.loads(Path(result["artifact_ref"]).read_text(encoding="utf-8"))

        self.assertEqual(artifact["provenance"]["execution_policy"], "fail_fast")
        self.assertEqual(
            artifact["provenance"]["steps"][3]["input_bindings"][0]["source_step"],
            "filter-admin",
        )
        self.assertNotIn("args", json.dumps(artifact["provenance"]))
        serialized = json.dumps(artifact)
        # Geometry is now a first-class, bounded result contract.  Raw step
        # arguments remain excluded, while the normalized geometry evidence is
        # intentionally persisted for Console/artifact/recovery consistency.
        geometry = artifact["result"]["geometry"]
        self.assertIn(geometry["status"], {"unknown", "no_geometry", "real_geometry", "boundary_geometry", "truncated_geometry"})
        self.assertIn('"geometry":', serialized)
        self.assertNotIn('"api_key":', serialized)


if __name__ == "__main__":
    unittest.main()
