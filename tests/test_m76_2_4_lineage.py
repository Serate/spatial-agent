import tempfile
import time
import unittest
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.service import AgentService
from serve_api import AgentApiHandler
from result_contract import build_result_contract


class M7624LineageTests(unittest.TestCase):
    def test_async_observation_and_session_history_share_run_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            try:
                submitted = service.run_async(
                    request="你好",
                    session_id="conversation-lineage",
                    planner="rule",
                    backend="memory",
                )
                deadline = time.monotonic() + 5
                envelope = None
                while time.monotonic() < deadline:
                    envelope = service.get_run(submitted["run_id"])
                    if envelope["status"] == "COMPLETED":
                        break
                    time.sleep(0.01)
                observation = service.get_async_observability(submitted["run_id"])
                history = service.list_session_runs("conversation-lineage")["runs"]
            finally:
                service._async_executor.shutdown(wait=True)

        self.assertIsNotNone(envelope)
        self.assertEqual(envelope["status"], "COMPLETED")
        self.assertEqual(observation["lineage"]["run_id"], submitted["run_id"])
        self.assertTrue(observation["lineage"]["trace"]["available"])
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["lineage"]["run_id"], submitted["run_id"])
        self.assertFalse(history[0]["lineage"]["trace"]["available"])
        self.assertTrue(history[0]["lineage"]["trace"]["deferred"])

    def test_comparisons_index_each_child_run_and_the_collection(self):
        service = AgentService()
        threshold = service.compare_buildability("洪山区", [15, 20], backend="memory")
        region = service.compare_buildability_regions(
            ["洪山区", "江夏区"], threshold=20, backend="memory"
        )

        threshold_ids = [row["run_id"] for row in threshold["results"]]
        self.assertEqual(threshold["lineage"]["run_ids"], threshold_ids)
        self.assertTrue(all(row["lineage"]["run_id"] == row["run_id"] for row in threshold["results"]))
        region_ids = [row["run_id"] for row in region["results"]]
        self.assertEqual(region["lineage"]["run_ids"], region_ids)
        self.assertTrue(all(row["lineage"]["run_id"] == row["run_id"] for row in region["results"]))

    def test_retry_count_is_part_of_the_shared_lineage_contract(self):
        payload = {
            "run_id": "retry-lineage",
            "status": "COMPLETED",
            "answer": "已完成",
            "retry_count": 2,
            "steps": [],
            "plan": {"output": {"type": "direct_answer"}},
        }

        lineage = build_result_contract(payload)["lineage"]

        self.assertEqual(lineage["retry"], {
            "available": True,
            "count": 2,
            "ref": "retry-lineage",
        })

    def test_http_history_and_comparison_keep_lineage_references(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            run = _post_json(
                server.server_address[1],
                {"request": "查询洪山区行政区边界", "session_id": "conversation-http-lineage"},
                "/runs",
            )
            history = _get_json(
                server.server_address[1],
                "/sessions/conversation-http-lineage/runs",
            )
            comparison = _post_json(
                server.server_address[1],
                {"admin_name": "洪山区", "thresholds": [20], "backend": "memory"},
                "/comparisons",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(history["runs"][0]["lineage"]["run_id"], run["run_id"])
        self.assertEqual(
            comparison["lineage"]["run_ids"],
            [comparison["results"][0]["run_id"]],
        )
        self.assertEqual(
            comparison["results"][0]["lineage"]["run_id"],
            comparison["results"][0]["run_id"],
        )


def _get_json(port, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()


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
        return json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()
