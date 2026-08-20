"""Small offline developer gate for the shared Agent Runtime contract."""

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from evaluation.contract_harness import compare_results
from serve_api import AgentApiHandler


ROOT = Path(__file__).resolve().parents[1]


class DevGateTests(unittest.TestCase):
    def test_runtime_result_and_artifact_share_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = AgentService(artifact_store=ArtifactStore(str(root / "service-runs")))
            direct = service.run(
                "查询洪山区行政区边界",
                session_id="dev-gate",
                planner="rule",
                backend="memory",
                export_artifact=True,
            )
            service_artifact = json.loads(
                Path(direct["artifact_ref"]).read_text(encoding="utf-8")
            )

            cli = subprocess.run(
                [
                    sys.executable,
                    "run_demo.py",
                    "查询洪山区行政区边界",
                    "--planner",
                    "rule",
                    "--backend",
                    "memory",
                    "--export-artifact",
                    "--artifact-root",
                    str(root / "cli-runs"),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            cli_payload = json.loads(cli.stdout)
            cli_artifact = json.loads(
                Path(cli_payload["artifact_ref"]).read_text(encoding="utf-8")
            )

            handler_service = service

            class TestHandler(AgentApiHandler):
                service = handler_service

            server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = HTTPConnection(
                    "127.0.0.1", server.server_address[1], timeout=5
                )
                body = json.dumps(
                    {
                        "request": "查询洪山区行政区边界",
                        "session_id": "dev-http",
                        "planner": "rule",
                        "backend": "memory",
                        "export_artifact": True,
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                connection.request(
                    "POST",
                    "/runs",
                    body=body,
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                http_payload = json.loads(response.read().decode("utf-8"))
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                TestHandler.service._async_executor.shutdown(wait=True)

        self.assertEqual(direct["status"], "COMPLETED")
        self.assertEqual(direct["result"]["type"], "admin_area_result")
        self.assertTrue(direct["answer"])
        self.assertTrue(direct["trace_summary"])
        self.assertEqual(response.status, 200)
        self.assertEqual(
            compare_results([direct, cli_payload, http_payload, service_artifact, cli_artifact]),
            [],
        )

    def test_clarification_follow_up_is_session_scoped(self):
        service = AgentService()
        first = service.run("查询行政区边界", session_id="dev-clarification")
        second = service.run("洪山区", session_id="dev-clarification")

        self.assertEqual(first["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(second["status"], "COMPLETED")
        self.assertIn("memory://range/admin_areas", second["answer"])

    def test_service_smoke_covers_raster_and_tool_dispatch(self):
        service = AgentService()
        raster = service.run("查询DEM栅格元数据", session_id="dev-raster")
        road = service.run(
            "查询距离主干道500米以内、坡度超过25度的区域。",
            session_id="dev-road",
        )

        self.assertEqual(raster["status"], "COMPLETED")
        self.assertEqual(raster["steps"][0]["tool"], "get_raster_metadata")
        self.assertEqual(road["status"], "COMPLETED")
        self.assertTrue(road["steps"])


if __name__ == "__main__":
    unittest.main()
