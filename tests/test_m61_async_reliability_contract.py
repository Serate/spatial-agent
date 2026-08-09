import tempfile
import time
import unittest
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.service import AgentService
from agent.sqlite_store import SQLiteStateStore
from serve_api import AgentApiHandler


def _wait_for_terminal(service, run_id, timeout=3.0):
    deadline = time.time() + timeout
    snapshot = None
    while time.time() < deadline:
        try:
            snapshot = service.get_run(run_id)
        except ValueError:
            pass
        if snapshot and snapshot["status"] not in {"CREATED", "PLANNING", "EXECUTING"}:
            store = getattr(service, "_state_store", None)
            if store is None:
                return snapshot
            job = store.get_async_job(run_id)
            if job is None or job.get("status") not in {"QUEUED", "RUNNING"}:
                return snapshot
        time.sleep(0.01)
    raise AssertionError("async run did not reach a terminal state")


class M61AsyncReliabilityContractTests(unittest.TestCase):
    def test_repeated_post_async_requests_share_one_run(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))

            class TestHandler(AgentApiHandler):
                pass

            TestHandler.service = service
            server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                body = json.dumps({
                    "request": "你好",
                    "session_id": "m61-post-duplicate",
                    "planner": "rule",
                    "backend": "memory",
                }).encode("utf-8")
                responses = []
                for _ in range(2):
                    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                    try:
                        connection.request(
                            "POST", "/runs/async", body=body,
                            headers={"Content-Type": "application/json"},
                        )
                        response = connection.getresponse()
                        responses.append(json.loads(response.read().decode("utf-8")))
                    finally:
                        connection.close()
                _wait_for_terminal(service, responses[0]["run_id"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service._async_executor.shutdown(wait=True)

        self.assertEqual(responses[0]["run_id"], responses[1]["run_id"])
        self.assertTrue(responses[1]["idempotent"])

    def test_repeated_async_submission_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            request = {
                "request": "查询洪山区行政区边界",
                "session_id": "m61-duplicate",
                "planner": "rule",
                "backend": "memory",
            }
            first = service.run_async(**request)
            second = service.run_async(**request)
            completed = _wait_for_terminal(service, first["run_id"])
            runs = service.list_session_runs("m61-duplicate")["runs"]

        self.assertEqual(first["run_id"], second["run_id"])
        self.assertTrue(second["reused"])
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(len(runs), 1)

    def test_explicit_run_id_is_idempotent_for_async_and_sync_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            service = AgentService(state_db_path=path)
            first = service.run_async(
                request="你好",
                session_id="m61-explicit",
                planner="rule",
                backend="memory",
                run_id="m61-fixed-run",
            )
            second = service.run_async(
                request="完全不同的请求",
                session_id="m61-explicit",
                planner="rule",
                backend="memory",
                run_id="m61-fixed-run",
            )
            completed = _wait_for_terminal(service, first["run_id"])
            sync_replay = service.run(
                request="再次不同的请求",
                session_id="m61-explicit",
                planner="rule",
                backend="memory",
                run_id="m61-fixed-run",
            )

        self.assertEqual(first["run_id"], second["run_id"])
        self.assertTrue(second["reused"])
        self.assertEqual(completed["request"], "你好")
        self.assertEqual(sync_replay["request"], "你好")
        self.assertEqual(sync_replay["run_id"], "m61-fixed-run")

    def test_recreated_service_recovers_a_queued_job(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            store = SQLiteStateStore(path)
            store.create_async_job(
                "m61-recovery-key",
                "m61-recovery-run",
                {
                    "request": "查询DEM栅格元数据",
                    "session_id": "m61-recovery",
                    "planner": "rule",
                    "backend": "memory",
                    "run_id": "m61-recovery-run",
                },
            )

            restored = AgentService(state_db_path=path)
            completed = _wait_for_terminal(restored, "m61-recovery-run")

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["run_id"], "m61-recovery-run")

    def test_clear_session_removes_persisted_async_deduplication_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            service = AgentService(state_db_path=path)
            first = service.run_async(
                request="你好",
                session_id="m61-clear-async",
                planner="rule",
                backend="memory",
            )
            _wait_for_terminal(service, first["run_id"])
            service.clear_session("m61-clear-async")
            second = service.run_async(
                request="你好",
                session_id="m61-clear-async",
                planner="rule",
                backend="memory",
            )
            _wait_for_terminal(service, second["run_id"])

        self.assertNotEqual(first["run_id"], second["run_id"])


if __name__ == "__main__":
    unittest.main()
