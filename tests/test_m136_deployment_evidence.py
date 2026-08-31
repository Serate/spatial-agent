"""M136 cross-entry Runtime Context and deployment evidence checks."""

import json
import tempfile
import time
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from domains.text.runtime import build_text_runtime
from evaluation.contract_harness import compare_results


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


def _wait_for_terminal(service, run_id, timeout=5.0):
    terminal = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT", "REJECTED", "NEEDS_CLARIFICATION"}
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = service.get_run(run_id)
        if latest.get("status") in terminal:
            return latest
        time.sleep(0.01)
    raise AssertionError("async run did not reach terminal state: {!r}".format(latest))


class M136DeploymentEvidenceTests(unittest.TestCase):
    def test_async_poll_restart_and_idempotent_replay_preserve_context(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "state.db")
            first_service = AgentService(state_db_path=database, domain_id="text")
            submitted = first_service.run_async(
                request="请摘要这段异步文本并保留部署证据。",
                session_id="m136-async",
                planner="rule",
                backend="memory",
                idempotency_key="m136-async-key",
            )
            try:
                completed = _wait_for_terminal(first_service, submitted["run_id"])
                observation = first_service.get_async_observability(submitted["run_id"])
            finally:
                first_service.close()

            second_service = AgentService(state_db_path=database, domain_id="text")
            try:
                restored = second_service.get_run(submitted["run_id"])
                replay = second_service.run_async(
                    request="另一段文本",
                    session_id="other-session",
                    planner="rule",
                    backend="memory",
                    idempotency_key="m136-async-key",
                )
            finally:
                second_service.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(
            observation["runtime_context_fingerprint"],
            completed["runtime_context"]["fingerprint"],
        )
        self.assertEqual(compare_results([completed, restored]), [])
        self.assertTrue(replay["idempotent"])
        self.assertEqual(replay["run_id"], submitted["run_id"])

    def test_domain_action_artifact_recovery_preserves_context_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(artifact_store=ArtifactStore(directory))
            try:
                action = service.execute_action(
                    "gis.buildability_threshold_comparison",
                    {
                        "admin_name": "洪山区",
                        "thresholds": [20],
                        "planner": "rule",
                        "backend": "memory",
                    },
                    backend="memory",
                )
                recovered = service.get_action_execution(action["action_execution_id"])
            finally:
                service.close()

        self.assertEqual(compare_results([action, recovered]), [])
        fingerprint = action["runtime_context"]["fingerprint"]
        self.assertEqual(action["result"]["runtime_context"]["fingerprint"], fingerprint)
        self.assertEqual(action["result"]["model_evidence"]["context_fingerprint"], fingerprint)
        self.assertEqual(
            recovered["result"]["model_evidence"]["context_fingerprint"],
            fingerprint,
        )

    def test_text_and_gis_contexts_are_distinct_and_self_describing(self):
        gis_service = AgentService()
        text_service = AgentService(runtime_factory=_text_runtime_factory, domain_id="text")
        try:
            gis = gis_service.run("查询洪山区行政区边界", backend="memory")
            text = text_service.run("请摘要这段文本。", backend="memory")
        finally:
            gis_service.close()
            text_service.close()

        gis_context = gis["runtime_context"]
        text_context = text["runtime_context"]
        self.assertEqual(gis_context["domain_id"], "gis")
        self.assertEqual(text_context["domain_id"], "text")
        self.assertNotEqual(gis_context["fingerprint"], text_context["fingerprint"])
        for payload in (gis, text):
            fingerprint = payload["runtime_context"]["fingerprint"]
            self.assertEqual(payload["provenance"]["runtime_context_fingerprint"], fingerprint)
            self.assertEqual(payload["result"]["model_evidence"]["context_fingerprint"], fingerprint)
            json.dumps(payload["result"]["model_evidence"], ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
