"""M211: action failure and idempotent replay share one error contract."""

import json
import tempfile
import unittest
from pathlib import Path

from agent.api_contract import error_response
from agent.artifact_store import ArtifactStore
from agent.service import AgentService


class M211ActionFailureReplayTests(unittest.TestCase):
    def test_semantic_failure_replay_preserves_error_identity_and_artifact(self):
        payload = {"admin_name": "洪山区", "thresholds": []}
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(artifact_store=ArtifactStore(directory))
            try:
                with self.assertRaises(ValueError) as first:
                    service.execute_action(
                        "gis.buildability_threshold_comparison",
                        payload,
                        backend="memory",
                        idempotency_key="m211-failure",
                    )
            finally:
                service.close()

            service = AgentService(artifact_store=ArtifactStore(directory))
            try:
                with self.assertRaises(ValueError) as replay:
                    service.execute_action(
                        "gis.buildability_threshold_comparison",
                        payload,
                        backend="memory",
                        idempotency_key="m211-failure",
                    )
                artifact = json.loads(
                    Path(first.exception.artifact_ref).read_text(encoding="utf-8")
                )
            finally:
                service.close()

        self.assertEqual(error_response(first.exception), error_response(replay.exception))
        self.assertEqual(first.exception.action_id, "gis.buildability_threshold_comparison")
        self.assertEqual(first.exception.code, "action_execution_failed")
        self.assertEqual(
            first.exception.action_execution_id,
            replay.exception.action_execution_id,
        )
        self.assertEqual(first.exception.artifact_ref, replay.exception.artifact_ref)
        self.assertEqual(artifact["status"], "FAILED")
        self.assertEqual(artifact["idempotency_key"], "m211-failure")
        self.assertEqual(artifact["action_id"], first.exception.action_id)


if __name__ == "__main__":
    unittest.main()
