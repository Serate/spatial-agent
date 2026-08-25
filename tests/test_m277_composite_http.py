"""M277: stdlib transport routes Composite through HTTPApplication."""

from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import serve_api


class _Composite:
    def run(self, payload, *, session_id):
        return {
            "schema_version": "spatial-agent.composite-coordinator.v1",
            "status": "COMPLETED",
            "state": "completed",
            "session_id": session_id,
            "request_keys": sorted(payload.keys()),
        }


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


class M277CompositeHttpTests(unittest.TestCase):
    def test_stdlib_composite_route_uses_shared_http_application(self):
        original = serve_api.composite_application
        serve_api.composite_application = _Composite()
        class Handler(serve_api.AgentApiHandler):
            pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, payload = _post(
                server.server_address[1],
                "/composite-runs",
                {"session_id": "m277-stdlib", "components": []},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            serve_api.composite_application = original

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["session_id"], "m277-stdlib")
        self.assertIn("components", payload["request_keys"])


if __name__ == "__main__":
    unittest.main()
