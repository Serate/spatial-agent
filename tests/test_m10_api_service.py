import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

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
        self.assertIn("已找到", second["answer"])
        range_step = next(
            step for step in second["steps"] if step["tool"] == "range_query"
        )
        self.assertEqual(
            range_step["result"]["result_ref"],
            "memory://range/admin_areas",
        )

    def test_service_validates_request(self):
        service = AgentService()
        with self.assertRaises(ValueError):
            service.run("")


class M10HttpApiTests(unittest.TestCase):
    def test_http_api_serves_console(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            connection.request("GET", "/")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(response.status, 200)
        self.assertIn("空间智能体控制台", body)

    def test_http_api_serves_exported_artifacts_and_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runs = root / "runs"
            geojson = root / "geojson"
            runs.mkdir()
            geojson.mkdir()
            (runs / "run-1.json").write_text('{"status":"COMPLETED"}', encoding="utf-8")
            (geojson / "run-1.geojson").write_text('{"type":"FeatureCollection"}', encoding="utf-8")

            class TestHandler(AgentApiHandler):
                service = AgentService()
                artifact_root = runs
                geojson_root = geojson

            server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                artifact = _get_json(server.server_address[1], "/artifacts/runs/run-1.json")
                geojson_payload = _get_json(server.server_address[1], "/artifacts/geojson/run-1.geojson")
                traversal = _get_json(
                    server.server_address[1],
                    "/artifacts/runs/../geojson/run-1.geojson",
                    expected_status=404,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(artifact["status"], "COMPLETED")
        self.assertEqual(geojson_payload["type"], "FeatureCollection")
        self.assertEqual(traversal["error"], "not found")

    def test_http_api_health_check(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = _get_json(server.server_address[1], "/health")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(payload["status"], "ok")
        self.assertIs(payload["capabilities"]["memory_backend"], True)
        self.assertIn("local_gis_backend", payload["capabilities"])
        self.assertIn("live_llm", payload["capabilities"])
        self.assertIn("live_llm_configured", payload["capabilities"])
        self.assertIn("live_llm_network", payload["capabilities"])
        self.assertIn("geopandas", payload["dependencies"])
        self.assertIn("rasterio", payload["dependencies"])
        self.assertIn("dataset_root_exists", payload["data"])
        self.assertIn("python", payload)

    def test_http_api_console_includes_environment_status_panel(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            connection.request("GET", "/")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(response.status, 200)
        self.assertIn("正在检查运行环境", body)
        self.assertIn("capabilityStatus", body)
        self.assertNotIn("data-domain-control", body)
        self.assertIn("真实大模型", body)
        self.assertIn("对话", body)
        self.assertIn("发送", body)
        self.assertIn("新建会话", body)
        self.assertIn("清空对话", body)
        self.assertIn('<select id="session"', body)
        self.assertIn("对话1", body)
        self.assertIn("运行血缘", body)
        self.assertIn("空间智能体", body)
        self.assertIn("console_app.js", body)
        self.assertIn("console_renderer_registry.js", body)
        self.assertIn("console_action_host.js", body)
        self.assertIn("console_gis_plugin.js", body)

    def test_http_api_returns_not_found_for_unknown_route(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = _get_json(server.server_address[1], "/missing", expected_status=404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(payload, {"error": "not found"})

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
        self.assertIn("已找到", second["answer"])

    def test_http_api_returns_an_individual_run_for_async_polling(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            created = _post_json(
                server.server_address[1],
                {"request": "查询洪山区行政区边界", "planner": "rule", "backend": "memory"},
            )
            payload = _get_json(
                server.server_address[1],
                "/runs/" + created["run_id"] + "?planner=rule&backend=memory",
            )
            missing = _get_json(
                server.server_address[1],
                "/runs/not-found?planner=rule&backend=memory",
                expected_status=404,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(payload["run_id"], created["run_id"])
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertIn("run not found", missing["error"])

    def test_runtime_reuses_completed_request_for_follow_up(self):
        runtime = AgentService()._runtime("rule", "memory")
        first = runtime.run("查询洪山区行政区边界", session_id="follow-up")
        second = runtime.run("继续分析这个结果", session_id="follow-up")

        self.assertEqual(first.status.value, "COMPLETED")
        self.assertEqual(second.status.value, "COMPLETED")
        self.assertIn("洪山区", second.resolved_request)

    def test_http_api_rejects_bad_request_payloads(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            empty_request = _post_json(
                server.server_address[1],
                {"request": ""},
                expected_status=400,
            )
            bad_backend = _post_json(
                server.server_address[1],
                {"request": ADMIN_NAME, "backend": "postgres"},
                expected_status=400,
            )
            bad_planner = _post_json(
                server.server_address[1],
                {"request": ADMIN_NAME, "planner": "random"},
                expected_status=400,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertIn("request must be a non-empty string", empty_request["error"])
        self.assertIn("backend must be one of", bad_backend["error"])
        self.assertIn("planner must be one of", bad_planner["error"])

    def test_http_api_retry_route_is_available(self):
        class TestHandler(AgentApiHandler):
            class FakeService:
                def retry(self, **kwargs):
                    return {"run_id": kwargs["run_id"], "status": "COMPLETED"}

            service = FakeService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = _post_json(
                server.server_address[1],
                {"planner": "rule", "backend": "memory"},
                path="/runs/run-1/retry",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(payload, {"run_id": "run-1", "status": "COMPLETED"})

    def test_http_api_cancel_route_is_available(self):
        class TestHandler(AgentApiHandler):
            class FakeService:
                def cancel(self, **kwargs):
                    return {
                        "run_id": kwargs["run_id"],
                        "status": "CANCEL_REQUESTED",
                        "current_status": "EXECUTING",
                    }

            service = FakeService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = _post_json(
                server.server_address[1],
                {"planner": "rule", "backend": "memory"},
                path="/runs/run-1/cancel",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(payload["status"], "CANCEL_REQUESTED")

    def test_http_api_async_run_route_is_available(self):
        class TestHandler(AgentApiHandler):
            class FakeService:
                def run_async(self, **kwargs):
                    return {"run_id": "async-1", "status": "QUEUED"}

            service = FakeService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = _post_json(
                server.server_address[1],
                {"request": "你好", "session_id": "async-http", "planner": "rule", "backend": "memory"},
                path="/runs/async",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(payload, {"run_id": "async-1", "status": "QUEUED"})

    def test_http_api_returns_structured_spatial_clarification(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = _post_json(
                server.server_address[1],
                {"request": "查询武汉城市绿地空间分布", "session_id": "clarification-http"},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(payload["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(payload["result"]["clarification"]["state"], "unmatched_spatial_capability")
        self.assertIn("空间对象", payload["clarification"]["missing"])

    def test_service_compares_buildability_thresholds(self):
        result = AgentService().compare_buildability(
            "洪山区", [15, 20], backend="memory"
        )

        self.assertEqual(result["thresholds"], [15.0, 20.0])
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["status"], "COMPLETED")


def _get_json(port, path, expected_status=200):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        if response.status != expected_status:
            raise AssertionError(data)
        return data
    finally:
        connection.close()


def _post_json(port, payload, expected_status=200, path="/runs"):
    body = json.dumps(payload).encode("utf-8")
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        if response.status != expected_status:
            raise AssertionError(data)
        return data
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
