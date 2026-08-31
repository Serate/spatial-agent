"""M126: Domain-owned evidence and action execution replay contracts."""

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.api_contract import error_response
from agent.service import AgentService
from domains.text.runtime import build_text_runtime
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
    data = json.loads(response.read().decode("utf-8"))
    connection.close()
    return response.status, data


class M126DomainEvidenceActionTests(unittest.TestCase):
    def test_text_runtime_and_release_evidence_stay_domain_neutral(self):
        service = AgentService(runtime_factory=_text_runtime_factory, domain_id="text")
        try:
            runtime = service.runtime_capabilities(backend="memory")
            release = service.release_evidence(backend="memory")
        finally:
            service.close()
        self.assertEqual(runtime["domain_id"], "text")
        self.assertEqual(runtime["data_readiness"], "not_applicable")
        self.assertEqual(release["domain_id"], "text")
        self.assertEqual(release["status"], "not_applicable")
        encoded = json.dumps(runtime, ensure_ascii=False).lower()
        for gis_marker in (
            "get_raster_metadata",
            "get_zonal_",
            "raster_metadata_result",
            "spatial_analysis_result",
            "admin_area_result",
            "洪山区",
        ):
            self.assertNotIn(gis_marker, encoded)

    def test_text_action_has_result_trace_artifact_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                response = service.execute_action(
                    "text.summarize",
                    {"text": "空间智能体需要清晰的执行证据。"},
                    backend="memory",
                )
                recovered = service.get_action_execution(response["action_execution_id"])
                artifact = json.loads(
                    Path(response["artifact_ref"]).read_text(encoding="utf-8")
                )
            finally:
                service.close()
        self.assertEqual(response["status"], "COMPLETED")
        self.assertTrue(response["action_execution"]["input_validated"])
        self.assertEqual(response["result"]["type"], "text_summary_result")
        self.assertEqual(response["result"]["action"]["id"], "text.summarize")
        self.assertEqual(response["trace_summary"][0], "Received action: text.summarize")
        self.assertEqual(recovered["action_execution_id"], response["action_execution_id"])
        self.assertEqual(recovered["result"]["type"], "text_summary_result")
        self.assertEqual(artifact["artifact_schema_version"], "spatial-agent.action-artifact.v1")

    def test_invalid_text_action_keeps_structured_failure_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                with self.assertRaises(ValueError) as raised:
                    service.execute_action("text.summarize", {}, backend="memory")
                exc = raised.exception
                recovered = service.get_action_execution(exc.action_execution_id)
            finally:
                service.close()
        self.assertEqual(exc.code, "action_invalid_input")
        self.assertEqual(error_response(exc)["action_error_code"], "action_invalid_input")
        self.assertEqual(recovered["status"], "FAILED")
        self.assertEqual(
            recovered["action_execution"]["input_validated"],
            False,
        )
        self.assertEqual(recovered["action_error_code"], "action_invalid_input")

    def test_dev_http_uses_selected_domain_for_release_and_action_recovery(self):
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
                release_status, release = _request(
                    server.server_address[1], "GET", "/release-evidence?backend=memory"
                )
                action_status, action = _request(
                    server.server_address[1],
                    "POST",
                    "/actions/text.summarize",
                    {"text": "HTTP action replay"},
                )
                recovery_status, recovered = _request(
                    server.server_address[1],
                    "GET",
                    "/action-executions/" + action["action_execution_id"],
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()
        self.assertEqual(release_status, 200)
        self.assertEqual(release["domain_id"], "text")
        self.assertEqual(action_status, 200)
        self.assertEqual(recovery_status, 200)
        self.assertEqual(recovered["result"]["action"]["domain_id"], "text")


if __name__ == "__main__":
    unittest.main()
