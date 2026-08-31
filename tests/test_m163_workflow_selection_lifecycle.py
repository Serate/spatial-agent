"""M163: workflow selection survives async, confirmation, and artifact recovery."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.decision_lifecycle import (
    DecisionLifecycleError,
    DecisionRecord,
    DecisionRequest,
    SQLiteDecisionStore,
)
from agent.service import AgentService
from domains.text.runtime import build_text_runtime
from evaluation.contract_harness import compare_results


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


def _wait_for_terminal(service: AgentService, run_id: str, timeout: float = 8.0):
    terminal = {
        "COMPLETED",
        "WAITING_FOR_DECISION",
        "REJECTED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
        "NEEDS_CLARIFICATION",
    }
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = service.get_run(run_id)
        if payload.get("status") in terminal:
            return payload
        time.sleep(0.01)
    raise AssertionError("async run did not reach a terminal state")


class M163WorkflowSelectionLifecycleTests(unittest.TestCase):
    def test_sqlite_decision_restore_is_domain_scoped_and_non_destructive(self):
        with tempfile.TemporaryDirectory(prefix="m163-decision-") as directory:
            store = SQLiteDecisionStore(str(Path(directory) / "state.db"))
            record = store.create(
                DecisionRequest(
                    subject_kind="run",
                    subject_id="m163-run",
                    domain_id="text",
                    session_id="m163",
                    decision_kind="plan_confirmation",
                    prompt="是否执行？",
                    options=("approve", "reject"),
                    subject_fingerprint="sha256:original",
                )
            )
            stale = DecisionRecord(
                **{**record.__dict__, "subject_fingerprint": "sha256:stale"}
            )
            restored = store.restore(stale)
            self.assertEqual(restored.subject_fingerprint, "sha256:original")

            foreign = DecisionRecord(
                **{**record.__dict__, "domain_id": "gis"}
            )
            with self.assertRaises(DecisionLifecycleError) as error:
                store.restore(foreign)
            self.assertEqual(error.exception.code, "decision_domain_mismatch")

    def test_selection_survives_async_confirmation_and_artifact_only_recovery(self):
        with tempfile.TemporaryDirectory(prefix="m163-selection-") as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            first = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=artifacts,
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                submitted = first.run_async(
                    request="请摘要一段异步文本，并在执行前确认。",
                    session_id="m163-selection",
                    planner="rule",
                    backend="memory",
                    require_confirmation=True,
                    export_artifact=True,
                    idempotency_key="m163-selection-key",
                )
                waiting = _wait_for_terminal(first, submitted["run_id"])
                waiting_observation = first.get_async_observability(
                    submitted["run_id"]
                )
                waiting_selection = waiting["result"]["planning"]["workflow_selection"]
                self.assertEqual(waiting["status"], "WAITING_FOR_DECISION")
                self.assertEqual(
                    waiting_selection,
                    waiting_observation["result_evidence"]["planning"][
                        "workflow_selection"
                    ],
                )
                decision = waiting["decision_evidence"]
                artifact = artifacts.read_run(submitted["run_id"], domain_id="text")
                self.assertIsInstance(artifact, dict)
                self.assertEqual(
                    artifact["async_result_evidence"]["planning"][
                        "workflow_selection"
                    ],
                    waiting_selection,
                )
            finally:
                first.close()

            recovered_service = AgentService(
                state_db_path=str(root / "empty-state.db"),
                artifact_store=artifacts,
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                recovered = recovered_service.get_run(submitted["run_id"])
                recovered_observation = recovered_service.get_async_observability(
                    submitted["run_id"]
                )
                self.assertEqual(
                    recovered["result"]["planning"]["workflow_selection"],
                    waiting_selection,
                )
                self.assertEqual(
                    recovered_observation["result_evidence"]["planning"][
                        "workflow_selection"
                    ],
                    waiting_selection,
                )

                approved = recovered_service.resolve_decision(
                    decision["decision_id"],
                    "approve",
                    expected_version=decision["version"],
                )
                self.assertEqual(approved["status"], "COMPLETED")
                self.assertEqual(
                    approved["result"]["planning"]["workflow_selection"],
                    waiting_selection,
                )
                self.assertEqual(compare_results([waiting, recovered]), [])
            finally:
                recovered_service.close()


if __name__ == "__main__":
    unittest.main()
