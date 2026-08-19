import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.failure_contract import FAILURE_SCHEMA_VERSION, failure_from_payload
from agent.models import PlanStep, TaskPlan
from agent.replanning import ReplanningPolicy
from agent.runtime import AgentRuntime
from agent.service import AgentService
from agent.tool_provider import ToolProviderError
from agent.tools import ToolRegistry
from serve_api import AgentApiHandler


class FailingProvider:
    provider_id = "failure-replay"

    def definitions(self):
        return {
            "probe": {
                "name": "probe",
                "permissions": ["demo:read"],
                "input_schema": {"type": "object"},
                "timeout_seconds": 2,
            }
        }

    def invoke(self, name, arguments):
        raise ToolProviderError(
            "upstream failure",
            provider_id=self.provider_id,
            code="upstream_timeout",
            retryable=True,
        )


class ProbePlanner:
    def plan(self, request, context=None):
        return TaskPlan(
            goal="probe provider",
            steps=[PlanStep("probe", "probe", {}, [])],
            output={"type": "vector_result"},
        )


class M97FailureContractTests(unittest.TestCase):
    def test_provider_failure_has_bounded_run_evidence(self):
        result = AgentRuntime(
            ProbePlanner(),
            ToolRegistry.from_provider(FailingProvider()),
            replan_policy=ReplanningPolicy(limit=0),
            allowed_permissions={"demo:read"},
        ).run("调用探针")

        payload = result.to_dict()
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["error_code"], "upstream_timeout")
        self.assertEqual(payload["failure"], {
            "schema_version": FAILURE_SCHEMA_VERSION,
            "status": "FAILED",
            "category": "provider",
            "code": "upstream_timeout",
            "phase": "execution",
            "retryable": True,
        })
        self.assertNotIn("upstream failure", json.dumps(payload["failure"]))

    def test_failed_service_run_keeps_failure_in_result_artifact_and_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = AgentService(
                artifact_store=ArtifactStore(str(root / "runs")),
                state_db_path=str(root / "agent.db"),
            )
            preview = service.preview(
                "查询洪山区行政区边界",
                session_id="failure-contract",
                planner="rule",
                backend="memory",
            )
            payload = service.run(
                "查询洪山区行政区边界",
                session_id="failure-contract",
                planner="rule",
                backend="memory",
                preview_fingerprint="sha256:mismatch",
                export_artifact=True,
            )
            artifact = json.loads(Path(payload["artifact_ref"]).read_text(encoding="utf-8"))
            restored = AgentService(state_db_path=str(root / "agent.db")).get_run(
                payload["run_id"], planner="rule", backend="memory"
            )

        self.assertEqual(preview["status"], "PLANNED")
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["failure"]["schema_version"], FAILURE_SCHEMA_VERSION)
        self.assertEqual(payload["result"]["failure"], payload["failure"])
        self.assertEqual(artifact["failure"], payload["failure"])
        self.assertEqual(artifact["result"]["failure"], payload["failure"])
        self.assertEqual(restored["failure"], payload["failure"])
        self.assertEqual(restored["result"]["failure"], payload["failure"])

    def test_old_failure_payload_is_normalized_without_raw_text(self):
        failure = failure_from_payload({
            "status": "FAILED",
            "error": "provider token https://private.invalid/secret",
            "error_category": "provider",
            "error_code": "upstream_timeout",
        })

        self.assertEqual(failure["schema_version"], FAILURE_SCHEMA_VERSION)
        self.assertEqual(failure["category"], "provider")
        self.assertEqual(failure["code"], "upstream_timeout")
        self.assertNotIn("private.invalid", json.dumps(failure))

    def test_http_failure_keeps_the_same_run_failure_contract(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection(*server.server_address, timeout=5)
            body = json.dumps({
                "request": "查询洪山区行政区边界",
                "session_id": "http-failure-contract",
                "planner": "rule",
                "backend": "memory",
                "preview_fingerprint": "sha256:mismatch",
            }, ensure_ascii=False).encode("utf-8")
            connection.request(
                "POST",
                "/runs",
                body=body,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["result"]["failure"], payload["failure"])
        self.assertEqual(payload["failure"]["schema_version"], FAILURE_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
