import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from serve_api import AgentApiHandler


ROOT = Path(__file__).parents[1]


class M81PlanEvidenceAcceptanceTests(unittest.TestCase):
    def test_http_result_and_artifact_share_template_planning_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            local_artifact_root = Path(directory) / "runs"
            local_geojson_root = Path(directory) / "geojson"

            class TestHandler(AgentApiHandler):
                service = AgentService(artifact_store=ArtifactStore(str(local_artifact_root)))
                artifact_root = local_artifact_root
                geojson_root = local_geojson_root

            server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                run = _post_json(
                    server.server_address[1],
                    {
                        "request": "查询洪山区行政区边界",
                        "planner": "rule",
                        "backend": "memory",
                        "export_artifact": True,
                    },
                    "/runs",
                )
                artifact_name = Path(run["artifact_ref"]).name
                artifact = _get_json(
                    server.server_address[1],
                    "/artifacts/runs/" + artifact_name,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                TestHandler.service._async_executor.shutdown(wait=True)

        evidence = run["plan_evidence"]
        planning = run["result"]["planning"]
        self.assertEqual(run["status"], "COMPLETED")
        self.assertEqual(planning["source"], evidence["source"])
        self.assertEqual(planning["planner_kind"], evidence["planner_kind"])
        self.assertTrue(planning["template_context_available"])
        self.assertIn("admin_boundary_query", planning["matched_template_ids"])
        self.assertIn("admin_boundary_query", planning["exact_template_ids"])
        self.assertEqual(
            artifact["plan_evidence"]["exact_template_ids"],
            planning["exact_template_ids"],
        )

    def test_console_uses_result_planning_evidence(self):
        source = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn("const planEvidence=envelope.planning||data.plan_evidence||{}", source)
        self.assertIn("计划来源", source)
        self.assertIn("exact_template_ids", source)


def _get_json(port, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        if response.status != 200:
            raise AssertionError(payload)
        return payload
    finally:
        connection.close()


def _post_json(port, payload, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        if response.status != 200:
            raise AssertionError(payload)
        return payload
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
