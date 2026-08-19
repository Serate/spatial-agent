import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from result_contract import build_result_contract


def _replanning_event():
    return {
        "failed_step_id": "screening",
        "failed_tool": "screen_tool",
        "failure_category": "tool_gate",
        "replanned_step_ids": ["health", "fallback"],
    }


class M102ReplanningRecoveryTests(unittest.TestCase):
    def test_nested_result_evidence_survives_legacy_artifact_rebuild(self):
        payload = {
            "run_id": "legacy-replan",
            "status": "COMPLETED",
            "result_type": "dataset_health_result",
            "result": {
                "replanning": {
                    "schema_version": "spatial-agent.replanning.v1",
                    "events": [_replanning_event()],
                }
            },
        }

        rebuilt = build_result_contract(payload)
        self.assertEqual(rebuilt["replanning"]["count"], 1)
        self.assertEqual(rebuilt["lineage"]["replanning"]["count"], 1)

    def test_artifact_roundtrip_rebuilds_the_same_replanning_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(root=Path(directory) / "runs")
            payload = {
                "run_id": "artifact-replan",
                "status": "COMPLETED",
                "request": "恢复分析",
                "result_type": "dataset_health_result",
                "replan_events": [_replanning_event()],
            }
            reference = store.write_run(payload)
            stored = store.read_run(Path(reference).stem)
            rebuilt = build_result_contract(stored)
            self.assertEqual(rebuilt["replanning"]["schema_version"], "spatial-agent.replanning.v1")
            self.assertEqual(rebuilt["replanning"]["events"][0]["failed_step_id"], "screening")
            self.assertEqual(rebuilt["lineage"]["replanning"]["ref"], "artifact-replan")


if __name__ == "__main__":
    unittest.main()
