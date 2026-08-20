"""One standard-library HTTP boundary check for the developer gate."""

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from agent.service import AgentService
from serve_api import AgentApiHandler


class HttpContractTests(unittest.TestCase):
    def test_health_endpoint_returns_json_contract(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            connection.request("GET", "/health")
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
            content_type = response.getheader("Content-Type", "")
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            TestHandler.service._async_executor.shutdown(wait=True)

        self.assertEqual(response.status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertIn("application/json", content_type)


if __name__ == "__main__":
    unittest.main()
