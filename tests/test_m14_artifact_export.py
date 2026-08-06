import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from serve_api import AgentApiHandler
from tests.test_m10_api_service import _post_json


ADMIN_QUERY = "\u67e5\u8be2\u6d2a\u5c71\u533a\u884c\u653f\u533a\u8fb9\u754c"


class M14ArtifactExportTests(unittest.TestCase):
    def test_service_can_export_run_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AgentService(artifact_store=ArtifactStore(tmpdir))
            result = service.run(ADMIN_QUERY, export_artifact=True)
            artifact_path = Path(result["artifact_ref"])

            self.assertTrue(artifact_path.exists())
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["run_id"], result["run_id"])
            self.assertEqual(payload["status"], "COMPLETED")
            self.assertIn("trace_summary", payload)
            self.assertIn("answer", payload)

    def test_service_does_not_export_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AgentService(artifact_store=ArtifactStore(tmpdir))
            result = service.run(ADMIN_QUERY)
        self.assertNotIn("artifact_ref", result)
        self.assertEqual(list(Path(tmpdir).glob("*.json")), [])

    def test_artifact_store_reports_run_metrics(self):
        with tempfile.TemporaryDirectory() as root:
            store = ArtifactStore(root=root)
            store.write_run({"run_id": "metrics-1", "status": "COMPLETED", "planner_metrics": {"usage": {"total_tokens": 12}}})
            metrics = store.metrics()

        self.assertEqual(metrics["run_count"], 1)
        self.assertEqual(metrics["total_tokens"], 12)

    def test_http_api_can_export_run_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            class TestHandler(AgentApiHandler):
                service = AgentService(artifact_store=ArtifactStore(tmpdir))

            server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = _post_json(
                    server.server_address[1],
                    {"request": ADMIN_QUERY, "export_artifact": True},
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            artifact_path = Path(result["artifact_ref"])
            self.assertTrue(artifact_path.exists())
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["run_id"], result["run_id"])


if __name__ == "__main__":
    unittest.main()
