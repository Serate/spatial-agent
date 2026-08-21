"""M148 artifact-only async result-evidence recovery contract."""

import json
import tempfile
import time
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from domains.text.runtime import build_text_runtime


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


def _wait_for_terminal(service, run_id, timeout=6.0):
    terminal = {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
        "REJECTED",
        "NEEDS_CLARIFICATION",
    }
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = service.get_run(run_id)
        if payload.get("status") in terminal:
            return payload
        time.sleep(0.01)
    raise AssertionError("async run did not reach terminal state")


class M148ArtifactAsyncRecoveryTests(unittest.TestCase):
    def test_artifact_only_recovery_preserves_bounded_async_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            first = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=artifacts,
                runtime_factory=_text_runtime_factory,
            )
            submitted = first.run_async(
                request="请摘要一段异步文本并保留证据。",
                session_id="m148-artifact-only",
                planner="rule",
                backend="memory",
                export_artifact=True,
                idempotency_key="m148-artifact-only-key",
            )
            try:
                completed = _wait_for_terminal(first, submitted["run_id"])
                live_observation = first.get_async_observability(submitted["run_id"])
            finally:
                first.close()

            artifact = artifacts.read_run(submitted["run_id"], domain_id="text")
            self.assertTrue(artifact["async_requested"])
            self.assertEqual(
                artifact["async_result_evidence"],
                live_observation["result_evidence"],
            )

            # A fresh database has no SQLite result or async job.  The run and
            # its bounded polling evidence must still be recoverable from the
            # artifact alone.
            recovered_service = AgentService(
                state_db_path=str(root / "empty-state.db"),
                artifact_store=artifacts,
                runtime_factory=_text_runtime_factory,
            )
            try:
                recovered = recovered_service.get_run(submitted["run_id"])
                recovered_observation = recovered_service.get_async_observability(
                    submitted["run_id"]
                )
            finally:
                recovered_service.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(
            recovered_observation["result_evidence"],
            live_observation["result_evidence"],
        )
        self.assertTrue(recovered_observation["recovered"])
        self.assertEqual(
            recovered["async_observability"]["result_evidence"],
            live_observation["result_evidence"],
        )

    def test_async_artifact_without_evidence_reports_unknown_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            artifacts.write_run(
                {
                    "run_id": "m148-legacy-async",
                    "status": "COMPLETED",
                    "domain_id": "text",
                    "request": "旧异步 artifact",
                    "steps": [],
                    "_async_requested": True,
                }
            )
            service = AgentService(
                artifact_store=artifacts,
                runtime_factory=_text_runtime_factory,
            )
            try:
                observation = service.get_async_observability("m148-legacy-async")
            finally:
                service.close()

        evidence = observation["result_evidence"]
        self.assertFalse(evidence["available"])
        self.assertEqual(evidence["state"], "unavailable")
        self.assertEqual(evidence["availability"], "unknown")
        self.assertEqual(evidence["reason_code"], "async_result_evidence_missing")
        self.assertEqual(evidence["source"], "run_artifact")
        self.assertNotIn("旧异步 artifact", json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
