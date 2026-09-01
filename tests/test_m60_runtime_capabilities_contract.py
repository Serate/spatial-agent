import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from agent.capability_catalog import capability_catalog
from serve_api import AgentApiHandler


def _snapshot(health_status="ready"):
    catalog = capability_catalog(environment="local")
    return {
        **catalog,
        "health_status": health_status,
        "updated_at": "2026-08-09T00:00:00Z",
        "data_evidence": {"dem": {"status": health_status}},
        "capabilities": [
            {
                **item,
                "runtime_evidence": {"datasets": {}},
            }
            for item in catalog["capabilities"]
        ],
    }


class M60RuntimeCapabilitiesContractTests(unittest.TestCase):
    def _request(self, path):
        class TestHandler(AgentApiHandler):
            service = None

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            connection.request("GET", path)
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
            return response.status, payload
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_standard_entry_returns_runtime_snapshot_contract(self):
        expected = _snapshot()
        with patch("serve_api.runtime_capability_snapshot", return_value=expected) as snapshot_mock:
            status, payload = self._request("/capabilities/runtime?max_files=1")

        self.assertEqual(status, 200)
        snapshot_mock.assert_called_once_with(max_files=1)
        self.assertEqual(payload["version"], "1.0")
        self.assertIn(payload["health_status"], {"ready", "degraded", "unavailable", "unknown"})
        self.assertTrue(payload["updated_at"])
        self.assertGreater(len(payload["capabilities"]), 0)
        self.assertIn("data_evidence", payload)
        for item in payload["capabilities"]:
            self.assertIn("runtime_evidence", item)
            self.assertIn("datasets", item["runtime_evidence"])

    def test_standard_entry_rejects_invalid_max_files(self):
        status, payload = self._request("/capabilities/runtime?max_files=0")
        self.assertEqual(status, 400)
        self.assertIn("max_files", payload["error"])

    def test_production_entry_uses_same_snapshot_and_bounds(self):
        try:
            from fastapi import HTTPException
            from production_api import runtime_capabilities
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                self.skipTest("requires production FastAPI dependencies")
            raise

        with patch("production_api.service") as service:
            service.runtime_capabilities.return_value = _snapshot()
            payload = runtime_capabilities(max_files=1)
            service.runtime_capabilities.assert_called_once_with(
                max_files=1,
                planner="openai",
                backend="local",
            )
        self.assertEqual(payload["version"], "1.0")
        self.assertEqual(payload["health_status"], "ready")
        with self.assertRaises(HTTPException) as context:
            runtime_capabilities(max_files=11)
        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
