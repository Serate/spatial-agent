import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from agent.service import AgentService
from serve_api import AgentApiHandler


GENERIC_ADMIN_QUERY = "\u67e5\u8be2\u884c\u653f\u533a\u8fb9\u754c"
ADMIN_NAME = "\u6d2a\u5c71\u533a"


class M10AgentServiceTests(unittest.TestCase):
    def test_service_preserves_follow_up_state_by_session(self):
        service = AgentService()
        first = service.run(GENERIC_ADMIN_QUERY, session_id="m10")
        self.assertEqual(first["status"], "NEEDS_CLARIFICATION")

        second = service.run(ADMIN_NAME, session_id="m10")
        self.assertEqual(second["status"], "COMPLETED")
        self.assertIn("memory://range/admin_areas", second["answer"])

    def test_service_validates_request(self):
        service = AgentService()
        with self.assertRaises(ValueError):
            service.run("")


class M10HttpApiTests(unittest.TestCase):
    def test_http_api_runs_agent_and_keeps_session_state(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            first = _post_json(
                server.server_address[1],
                {"request": GENERIC_ADMIN_QUERY, "session_id": "api-session"},
            )
            second = _post_json(
                server.server_address[1],
                {"request": ADMIN_NAME, "session_id": "api-session"},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(first["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(second["status"], "COMPLETED")
        self.assertIn("memory://range/admin_areas", second["answer"])


def _post_json(port, payload):
    body = json.dumps(payload).encode("utf-8")
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "POST",
            "/runs",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        if response.status != 200:
            raise AssertionError(data)
        return data
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
