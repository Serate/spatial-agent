import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from agent.service import AgentService
from serve_api import AgentApiHandler


def _post_json(port, payload, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        if response.status >= 400:
            raise AssertionError(data)
        return data
    finally:
        connection.close()


class M111OpenCapabilityContractTests(unittest.TestCase):
    def test_structured_clarification_is_catalog_labeled_across_service_and_http(self):
        request = "查询武汉城市绿地空间分布"
        direct = AgentService().run(
            request,
            session_id="m111-direct",
            planner="rule",
            backend="memory",
        )

        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            http = _post_json(
                server.server_address[1],
                {
                    "request": request,
                    "session_id": "m111-http",
                    "planner": "rule",
                    "backend": "memory",
                },
                "/runs",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        for payload in (direct, http):
            clarification = payload["clarification"]
            self.assertEqual(clarification["schema_version"], "spatial-agent.clarification.v1")
            self.assertTrue(
                any(
                    item["id"] == "admin_boundary_query"
                    and item["label"] == "行政区边界查询"
                    for item in clarification["suggested_capability_details"]
                )
            )
            self.assertEqual(payload["result"]["clarification"], clarification)

        self.assertEqual(direct["clarification"], http["clarification"])

    def test_open_capability_preview_is_consistent_across_service_and_http(self):
        request = "请概括江夏区的道路和水体分布"
        direct = AgentService().preview(
            request,
            session_id="m111-preview-direct",
            planner="rule",
            backend="memory",
        )

        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            http = _post_json(
                server.server_address[1],
                {
                    "request": request,
                    "session_id": "m111-preview-http",
                    "planner": "rule",
                    "backend": "memory",
                },
                "/runs/preview",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(direct["status"], "PLANNED")
        for field in (
            "status",
            "result_type",
            "request_facts",
            "plan",
            "dag",
            "plan_evidence",
            "execution",
        ):
            self.assertEqual(direct.get(field), http.get(field), field)
        self.assertEqual(
            [step["tool"] for step in direct["plan"]["steps"]],
            ["get_zonal_vector_summary"],
        )


if __name__ == "__main__":
    unittest.main()
