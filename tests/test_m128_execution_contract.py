"""M128: one bounded execution projection for Runs and Domain Actions."""

import json
import tempfile
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from tests.console_source import read_console_source
import threading

from agent.artifact_store import ArtifactStore
from agent.execution_contract import EXECUTION_RECORD_SCHEMA_VERSION, execution_record_summary
from agent.service import AgentService
from domains.text.runtime import build_text_runtime
from evaluation.contract_harness import normalize_execution, normalize_result


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
    return response.status, json.loads(raw.decode("utf-8"))


class M128ExecutionContractTests(unittest.TestCase):
    def test_run_and_action_expose_the_same_bounded_execution_record_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                run = service.run(
                    "请总结这段文本：空间数据需要明确来源。",
                    backend="memory",
                    export_artifact=True,
                )
                action = service.execute_action(
                    "text.summarize",
                    {"text": "空间数据需要明确来源。"},
                    backend="memory",
                )
            finally:
                service.close()

            run_artifact = json.loads(
                Path(run["artifact_ref"]).read_text(encoding="utf-8")
            )
            action_artifact = json.loads(
                Path(action["artifact_ref"]).read_text(encoding="utf-8")
            )

        self.assertEqual(run["execution_record"]["schema_version"], EXECUTION_RECORD_SCHEMA_VERSION)
        self.assertEqual(action["execution_record"]["schema_version"], EXECUTION_RECORD_SCHEMA_VERSION)
        self.assertEqual(run["execution_record"]["kind"], "run")
        self.assertEqual(action["execution_record"]["kind"], "action")
        self.assertEqual(run["execution_record"]["status"], "COMPLETED")
        self.assertEqual(action["execution_record"]["status"], "COMPLETED")
        self.assertEqual(run_artifact["execution_record"], run["execution_record"])
        self.assertEqual(action_artifact["execution_record"], action["execution_record"])
        self.assertEqual(
            run["result"]["execution"]["schema_version"],
            EXECUTION_RECORD_SCHEMA_VERSION,
        )
        self.assertEqual(action["result"]["execution"]["kind"], "action")
        for record in (run["execution_record"], action["execution_record"]):
            self.assertIn("id", record)
            self.assertIn("trace_count", record)
            self.assertIn("artifact_available", record)
            self.assertNotIn("request", record)
            self.assertNotIn("text", record)

    def test_runtime_result_also_exposes_the_same_record_before_service_formatting(self):
        runtime = build_text_runtime("rule", "memory")
        result = runtime.run("请总结：Runtime 结果也需要统一记录。")
        payload = result.to_dict()
        self.assertEqual(payload["execution_record"]["kind"], "run")
        self.assertEqual(
            payload["execution_record"]["schema_version"],
            EXECUTION_RECORD_SCHEMA_VERSION,
        )

    def test_failed_action_execution_record_preserves_retry_safe_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                with self.assertRaises(ValueError) as caught:
                    service.execute_action(
                        "text.summarize",
                        {},
                        backend="memory",
                        idempotency_key="m128-failure",
                    )
                error = caught.exception
                recovered = service.get_action_execution(error.action_execution_id)
            finally:
                service.close()

        record = recovered["execution_record"]
        self.assertEqual(record["kind"], "action")
        self.assertEqual(record["status"], "FAILED")
        self.assertEqual(record["id"], error.action_execution_id)
        self.assertTrue(record["idempotency_key_present"])
        self.assertTrue(record["input_fingerprint_present"])
        self.assertEqual(record["error_code"], "action_invalid_input")

    def test_contract_harness_keeps_execution_projection_transport_neutral(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                run = service.run("请总结：契约需要可恢复。", backend="memory")
                action = service.execute_action(
                    "text.summarize",
                    {"text": "契约需要可恢复。"},
                    backend="memory",
                )
            finally:
                service.close()

        normalized_run = normalize_result(run).as_dict()
        normalized_action = normalize_execution(action)
        self.assertEqual(normalized_run["execution"]["kind"], "run")
        self.assertEqual(normalized_action["kind"], "action")
        self.assertEqual(normalized_run["execution"]["schema_version"], EXECUTION_RECORD_SCHEMA_VERSION)
        self.assertEqual(normalized_action["schema_version"], EXECUTION_RECORD_SCHEMA_VERSION)
        self.assertNotIn("id", normalized_run["execution"])
        self.assertNotIn("artifact_ref", normalized_action)

    def test_console_renders_the_domain_neutral_execution_record(self):
        source = read_console_source(Path(__file__).parents[1])
        self.assertIn("renderExecutionRecord", source)
        self.assertIn("execution_record", source)
        self.assertIn("统一执行记录", source)

    def test_sqlite_async_recovery_rebuilds_the_same_execution_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "state.db")
            first = AgentService(
                state_db_path=db_path,
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                submitted = first.run_async(
                    request="请总结：异步结果必须可恢复。",
                    backend="memory",
                    export_artifact=True,
                    session_id="m128-async",
                )
                for _ in range(200):
                    current = first.get_run(submitted["run_id"])
                    if current["status"] == "COMPLETED":
                        break
                    time.sleep(0.01)
                completed = first.get_run(submitted["run_id"])
                expected = completed["execution_record"]
                async_observation = first.get_async_observability(submitted["run_id"])
            finally:
                first.close()

            second = AgentService(
                state_db_path=db_path,
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                restored = second.get_run(submitted["run_id"])
                restored_async_observation = second.get_async_observability(submitted["run_id"])
            finally:
                second.close()

            artifact = json.loads(
                Path(completed["artifact_ref"]).read_text(encoding="utf-8")
            )

        self.assertEqual(restored["status"], "COMPLETED")
        self.assertEqual(restored["execution_record"], expected)
        self.assertEqual(restored["result"]["execution"]["kind"], "run")
        expected_summary = execution_record_summary(expected)
        self.assertEqual(async_observation["result_evidence"]["execution"], expected_summary)
        self.assertEqual(
            restored_async_observation["result_evidence"]["execution"],
            expected_summary,
        )
        self.assertEqual(artifact["async_result_evidence"]["execution"], expected_summary)

    def test_development_http_preserves_run_and_action_execution_records(self):
        from serve_api import AgentApiHandler

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
                run_status, run = _request(
                    server.server_address[1],
                    "POST",
                    "/runs",
                    {
                        "request": "请总结：HTTP 结果也要可恢复。",
                        "backend": "memory",
                        "export_artifact": True,
                    },
                )
                action_status, action = _request(
                    server.server_address[1],
                    "POST",
                    "/actions/text.summarize",
                    {"text": "HTTP 动作也要可恢复。"},
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

        self.assertEqual(run_status, 200)
        self.assertEqual(action_status, 200)
        self.assertEqual(normalize_execution(run)["kind"], "run")
        self.assertEqual(normalize_execution(action)["kind"], "action")
        self.assertEqual(run["result"]["execution"]["schema_version"], EXECUTION_RECORD_SCHEMA_VERSION)
        self.assertEqual(action["result"]["execution"]["schema_version"], EXECUTION_RECORD_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
