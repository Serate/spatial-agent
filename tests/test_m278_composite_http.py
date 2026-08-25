import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from agent.application.http import HTTPApplication


class _CompositeRuns:
    def __init__(self):
        self.calls = []

    def submit_async(self, request, *, session_id, idempotency_key, export_artifact):
        self.calls.append(("submit_async", session_id, idempotency_key, export_artifact))
        return {"run_id": "composite-1", "status": "QUEUED", "reused": False}

    def get_run(self, run_id):
        self.calls.append(("get_run", run_id))
        return {"run_id": run_id, "result": {"type": "composite_result"}}

    def get_observability(self, run_id):
        self.calls.append(("observability", run_id))
        return {"run_id": run_id, "status": "COMPLETED"}

    def get_evidence(self, run_id):
        self.calls.append(("evidence", run_id))
        return {"run_id": run_id, "evidence_registry": {"available": True}}


class _TransportComposite:
    def run(self, payload, *, session_id):
        return {
            "schema_version": "spatial-agent.composite-coordinator.v1",
            "status": "COMPLETED",
            "state": "completed",
            "session_id": session_id,
            "request_keys": sorted(payload.keys()),
        }

    def submit_async(self, payload, *, session_id, idempotency_key, export_artifact):
        return {
            "run_id": "composite-http-1",
            "status": "QUEUED",
            "reused": False,
            "session_id": session_id,
            "idempotency_key": idempotency_key,
            "export_artifact": export_artifact,
        }

    def get_run(self, run_id):
        return {"run_id": run_id, "result": {"type": "composite_result"}}

    def get_observability(self, run_id):
        return {"run_id": run_id, "status": "COMPLETED"}

    def get_evidence(self, run_id):
        return {
            "run_id": run_id,
            "evidence_registry": {"available": True},
        }


def _get(port: int, path: str) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", path)
    response = connection.getresponse()
    value = json.loads(response.read().decode("utf-8"))
    status = response.status
    connection.close()
    return status, value


def _post(port: int, path: str, payload: dict) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request(
        "POST",
        path,
        body=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    value = json.loads(response.read().decode("utf-8"))
    status = response.status
    connection.close()
    return status, value


class M278CompositeHttpTests(unittest.TestCase):
    def test_composite_lifecycle_uses_shared_application_commands(self):
        composite = _CompositeRuns()
        application = HTTPApplication(object(), composite=composite)
        request = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "组合查询",
            "components": [],
        }

        submitted = application.execute(
            "composite_run_async",
            {
                **request,
                "session_id": "session-1",
                "idempotency_key": "idem-1",
                "export_artifact": True,
            },
        )
        detail = application.read("composite_run_detail", resource_id="composite-1")
        observation = application.read(
            "composite_observability", resource_id="composite-1"
        )
        evidence = application.read("composite_evidence", resource_id="composite-1")

        self.assertEqual(submitted["run_id"], "composite-1")
        self.assertEqual(detail["result"]["type"], "composite_result")
        self.assertEqual(observation["status"], "COMPLETED")
        self.assertTrue(evidence["evidence_registry"]["available"])
        self.assertEqual(
            [call[0] for call in composite.calls],
            ["submit_async", "get_run", "observability", "evidence"],
        )

    def test_stdlib_async_and_read_routes_share_composite_application(self):
        import serve_api

        original = serve_api.composite_application
        serve_api.composite_application = _TransportComposite()

        class Handler(serve_api.AgentApiHandler):
            pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, submitted = _post(
                server.server_address[1],
                "/composite-runs/async",
                {
                    "schema_version": "spatial-agent.composite-request.v1",
                    "request": "组合查询",
                    "components": [],
                    "session_id": "http-session",
                    "idempotency_key": "http-idem",
                },
            )
            detail_status, detail = _get(
                server.server_address[1], "/composite-runs/composite-http-1"
            )
            observation_status, observation = _get(
                server.server_address[1],
                "/composite-runs/composite-http-1/observability",
            )
            evidence_status, evidence = _get(
                server.server_address[1],
                "/composite-runs/composite-http-1/evidence",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            serve_api.composite_application = original

        self.assertEqual(status, 200)
        self.assertEqual(detail_status, 200)
        self.assertEqual(observation_status, 200)
        self.assertEqual(evidence_status, 200)
        self.assertEqual(submitted["run_id"], "composite-http-1")
        self.assertEqual(detail["result"]["type"], "composite_result")
        self.assertEqual(observation["status"], "COMPLETED")
        self.assertTrue(evidence["evidence_registry"]["available"])

    def test_fastapi_composite_routes_use_same_semantic_application(self):
        import production_api

        original = production_api.composite_application
        production_api.composite_application = _TransportComposite()
        payload = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "组合查询",
            "components": [],
            "session_id": "fastapi-session",
            "idempotency_key": "fastapi-idem",
        }
        try:
            submitted = production_api.composite_run_async(payload)
            detail = production_api.composite_detail("composite-http-1")
            observation = production_api.composite_observability("composite-http-1")
            evidence = production_api.composite_evidence("composite-http-1")
        finally:
            production_api.composite_application = original

        self.assertEqual(submitted["run_id"], "composite-http-1")
        self.assertEqual(detail["result"]["type"], "composite_result")
        self.assertEqual(observation["status"], "COMPLETED")
        self.assertTrue(evidence["evidence_registry"]["available"])


if __name__ == "__main__":
    unittest.main()
