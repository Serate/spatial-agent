"""M147 run artifact versioning, legacy compatibility, and path isolation."""

import json
import tempfile
import unittest
from pathlib import Path

from tests.console_source import read_console_source

from agent.artifact_store import ArtifactStore
from agent.contract_versions import RUN_ARTIFACT_SCHEMA_VERSION


class M147ArtifactCompatibilityTests(unittest.TestCase):
    def test_console_consumes_async_evidence_without_domain_result_branches(self):
        source = read_console_source(Path(__file__).parents[1])
        self.assertIn("renderAsyncResultEvidence", source)
        self.assertIn("result_evidence", source)
        self.assertIn("async-result-evidence", source)
        self.assertNotIn("outputType==='text_summary_result'", source)

    def test_current_and_legacy_run_artifacts_are_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ArtifactStore(root)
            current_ref = store.write_run(
                {
                    "run_id": "current-run",
                    "status": "COMPLETED",
                    "domain_id": "text",
                    "request": "请摘要文本",
                    "steps": [],
                }
            )
            legacy_path = root / "legacy-run.json"
            legacy_path.write_text(
                json.dumps(
                    {
                        "run_id": "legacy-run",
                        "status": "COMPLETED",
                        "domain_id": "text",
                        "request": "旧 artifact",
                        "steps": [],
                    }
                ),
                encoding="utf-8",
            )

            current = store.read_run("current-run", domain_id="text")
            legacy = store.read_run("legacy-run", domain_id="text")

        self.assertEqual(Path(current_ref).name, "current-run.json")
        self.assertEqual(current["artifact_schema_version"], RUN_ARTIFACT_SCHEMA_VERSION)
        self.assertEqual(legacy["run_id"], "legacy-run")
        self.assertNotIn("artifact_schema_version", legacy)

    def test_unknown_version_cross_domain_and_path_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ArtifactStore(root)
            (root / "future-run.json").write_text(
                json.dumps(
                    {
                        "run_id": "future-run",
                        "artifact_schema_version": "spatial-agent.run-artifact.v9",
                        "domain_id": "text",
                    }
                ),
                encoding="utf-8",
            )
            (root / "gis-run.json").write_text(
                json.dumps(
                    {
                        "run_id": "gis-run",
                        "domain_id": "gis",
                        "status": "COMPLETED",
                    }
                ),
                encoding="utf-8",
            )

            self.assertIsNone(store.read_run("future-run", domain_id="text"))
            self.assertIsNone(store.read_run("gis-run", domain_id="text"))
            self.assertIsNone(store.read_run("../gis-run", domain_id="gis"))
            self.assertIsNone(store.read_run(r"..\gis-run", domain_id="gis"))
            with self.assertRaises(ValueError):
                store.write_run({"run_id": "../escape", "status": "FAILED"})
            with self.assertRaises(ValueError):
                store.write_run({"run_id": r"..\escape", "status": "FAILED"})


if __name__ == "__main__":
    unittest.main()
