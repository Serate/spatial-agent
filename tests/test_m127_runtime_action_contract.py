"""M127: versioned evidence, action replay and Console visibility contracts."""

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from tests.console_source import read_console_source

from agent.artifact_store import ArtifactStore
from agent.domain_contract import release_evidence, runtime_evidence
from agent.observability import CollectingEmitter
from agent.service import AgentService
from domains.text.runtime import build_text_runtime
from evaluation.model_evaluation import evaluate_model_replay_suite_file
from serve_api import AgentApiHandler


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


def _request(port, method, path, payload=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    if response.getheader("Content-Type", "").startswith("application/json"):
        return response.status, json.loads(raw.decode("utf-8"))
    return response.status, raw


class _LegacyDomain:
    domain_id = "legacy"

    def runtime_evidence(self, *, max_files=10):
        return {"health_status": "ready", "data_readiness": "not_applicable"}

    def release_evidence(self, *, config_path=None, max_files=10):
        return {"status": "not_evaluated", "data_readiness": "not_applicable"}


class M127RuntimeActionContractTests(unittest.TestCase):
    def test_versioned_evidence_supports_provider_and_legacy_domain(self):
        service = AgentService(runtime_factory=_text_runtime_factory, domain_id="text")
        try:
            runtime = service.runtime_capabilities(backend="memory")
            release = service.release_evidence(backend="memory")
        finally:
            service.close()
        self.assertEqual(runtime["evidence_contract"]["schema_version"], "spatial-agent.domain-evidence.v1")
        self.assertEqual(runtime["evidence_contract"]["kind"], "runtime")
        self.assertEqual(release["evidence_contract"]["kind"], "release")
        self.assertEqual(runtime_evidence(_LegacyDomain())["evidence_contract"]["domain_id"], "legacy")
        self.assertEqual(release_evidence(_LegacyDomain())["evidence_contract"]["kind"], "release")

    def test_action_idempotency_reuses_success_and_rejects_conflicting_input(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                first = service.execute_action(
                    "text.summarize",
                    {"text": "同一输入只执行一次"},
                    backend="memory",
                    idempotency_key="m127-success",
                )
                second = service.execute_action(
                    "text.summarize",
                    {"text": "同一输入只执行一次"},
                    backend="memory",
                    idempotency_key="m127-success",
                )
                with self.assertRaisesRegex(ValueError, "conflicts"):
                    service.execute_action(
                        "text.summarize",
                        {"text": "不同输入"},
                        backend="memory",
                        idempotency_key="m127-success",
                    )
                actions = service.list_action_executions()
                metrics = service.metrics()["actions"]
            finally:
                service.close()
        self.assertEqual(first["action_execution_id"], second["action_execution_id"])
        self.assertTrue(second["idempotency_reused"])
        self.assertEqual(len(actions["actions"]), 1)
        self.assertEqual(metrics["count"], 1)

    def test_failed_action_idempotency_replays_failure_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                with self.assertRaises(ValueError) as first_error:
                    service.execute_action(
                        "text.summarize", {}, backend="memory", idempotency_key="m127-failure"
                    )
                with self.assertRaises(ValueError) as replay_error:
                    service.execute_action(
                        "text.summarize", {}, backend="memory", idempotency_key="m127-failure"
                    )
                recovered = service.get_action_execution(first_error.exception.action_execution_id)
            finally:
                service.close()
        self.assertEqual(first_error.exception.code, "action_invalid_input")
        self.assertEqual(replay_error.exception.code, "action_invalid_input")
        self.assertEqual(
            replay_error.exception.action_execution_id,
            first_error.exception.action_execution_id,
        )
        self.assertEqual(recovered["status"], "FAILED")

    def test_action_observability_is_bounded_and_machine_readable(self):
        emitter = CollectingEmitter(enabled=True)
        try:
            emitter.emit_action(
                execution_id="action-m127",
                action_id="text.summarize",
                domain_id="text",
                status="COMPLETED",
                duration_ms=3.5,
                attributes={"result_type": "text_summary_result", "raw_text": "must be dropped"},
            )
            self.assertEqual(len(emitter.events), 1)
            event = emitter.events[0]
            self.assertEqual(event["event"], "action")
            self.assertEqual(event["attributes"]["action_id"], "text.summarize")
            self.assertNotIn("raw_text", event["attributes"])
        finally:
            emitter.close()

    def test_dev_http_exposes_action_history_and_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory, domain_id="text",
            )

            class TextHandler(AgentApiHandler):
                pass

            TextHandler.service = service
            server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, action = _request(
                    server.server_address[1],
                    "POST",
                    "/actions/text.summarize",
                    {"text": "HTTP action evidence", "idempotency_key": "m127-http"},
                )
                history_status, history = _request(
                    server.server_address[1], "GET", "/action-executions?limit=5"
                )
                artifact_name = Path(action["artifact_ref"]).name
                artifact_status, artifact = _request(
                    server.server_address[1], "GET", "/artifacts/actions/" + artifact_name
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()
        self.assertEqual(status, 200)
        self.assertEqual(history_status, 200)
        self.assertEqual(artifact_status, 200)
        self.assertEqual(history["actions"][0]["action_execution_id"], action["action_execution_id"])
        self.assertEqual(artifact["artifact_schema_version"], "spatial-agent.action-artifact.v1")

    def test_console_consumes_generic_action_evidence_and_history(self):
        source = read_console_source(Path(__file__).parents[1])
        for token in (
            "renderActionEvidence",
            "/action-executions/",
            "artifactReferencePath",
            "data-action-execution",
            "/action-executions?limit=20",
            "idempotency_reused",
        ):
            self.assertIn(token, source)
        self.assertNotIn("needsRaster", source)

    def test_open_text_and_complex_gis_replay_share_sanitized_quality_report(self):
        report = evaluate_model_replay_suite_file(
            Path(__file__).parent / "fixtures" / "m127_domain_replay_suite.json"
        )
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["passed"], 2)
        self.assertTrue(all(item["metrics"]["token_usage"]["status"] == "reported" for item in report["results"]))


if __name__ == "__main__":
    unittest.main()
