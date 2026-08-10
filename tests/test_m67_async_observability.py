import json
import os
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from agent.models import AgentRunResult, RunStatus
from agent.service import AgentService
from agent.sqlite_store import SQLiteStateStore
from serve_api import AgentApiHandler


def _wait_for_job(service, run_id, statuses=None, timeout=5.0):
    statuses = statuses or {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}
    deadline = time.monotonic() + timeout
    snapshot = None
    while time.monotonic() < deadline:
        snapshot = service._state_store.get_async_job(run_id)
        if snapshot and snapshot.get("status") in statuses:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("async job did not reach {}: {!r}".format(statuses, snapshot))


class M67AsyncObservabilityTests(unittest.TestCase):
    def test_completed_job_exposes_timing_in_run_envelope_and_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            try:
                submitted = service.run_async(
                    request="查询DEM栅格元数据",
                    session_id="m67-completed",
                    planner="rule",
                    backend="memory",
                )
                job = _wait_for_job(service, submitted["run_id"])
                envelope = service.get_run(submitted["run_id"])
                metrics = service.metrics()
            finally:
                service._async_executor.shutdown(wait=True)

        observation = envelope["async_observability"]
        self.assertEqual(observation["status"], "COMPLETED")
        self.assertEqual(observation["phase"], "completed")
        self.assertEqual(observation["failure_category"], None)
        self.assertEqual(observation["last_event"], "completed")
        self.assertIsNotNone(observation["timestamps"]["submitted_at"])
        self.assertIsNotNone(observation["timestamps"]["started_at"])
        self.assertIsNotNone(observation["timestamps"]["finished_at"])
        self.assertGreaterEqual(observation["queue_wait_ms"], 0)
        self.assertGreaterEqual(observation["run_duration_ms"], 0)
        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(metrics["async_jobs"]["status_counts"]["COMPLETED"], 1)
        self.assertNotIn("request", observation)

    def test_worker_failure_is_classified_without_request_secret(self):
        secret = "sk-m67-request-secret"
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            try:
                with patch.object(
                    service,
                    "run",
                    side_effect=RuntimeError("worker crashed while handling " + secret),
                ):
                    submitted = service.run_async(
                        request="请处理 token=" + secret,
                        session_id="m67-failed",
                        planner="rule",
                        backend="memory",
                    )
                    job = _wait_for_job(service, submitted["run_id"])
                observation = service.get_async_observability(submitted["run_id"])
                metrics = service.metrics()
            finally:
                service._async_executor.shutdown(wait=True)

        self.assertEqual(job["status"], "FAILED")
        self.assertEqual(observation["phase"], "failed")
        self.assertEqual(observation["failure_category"], "worker_exception")
        self.assertNotIn(secret, repr(observation))
        self.assertNotIn(secret, repr(metrics))
        self.assertEqual(metrics["async_jobs"]["failure_categories"], {"worker_exception": 1})

    def test_restart_takeover_is_visible_and_does_not_expose_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            store = SQLiteStateStore(path)
            run_id = "m67-recovered-run"
            payload = {
                "request": "查询DEM栅格元数据",
                "session_id": "m67-recovered-secret-do-not-return",
                "planner": "rule",
                "backend": "memory",
                "run_id": run_id,
            }
            store.create_async_job("m67-recovery-key", run_id, payload)
            store.save(
                AgentRunResult(
                    run_id=run_id,
                    status=RunStatus.PLANNING,
                    request=payload["request"],
                    session_id=payload["session_id"],
                )
            )
            with store._connection() as connection:
                connection.execute(
                    "UPDATE async_jobs SET owner_pid = ?, status = 'RUNNING' WHERE run_id = ?",
                    (999999, run_id),
                )

            with patch("agent.service._process_is_alive", return_value=False):
                restarted = AgentService(state_db_path=path)
            try:
                job = _wait_for_job(restarted, run_id)
                observation = restarted.get_async_observability(run_id)
            finally:
                restarted._async_executor.shutdown(wait=True)

        self.assertEqual(job["status"], "COMPLETED")
        self.assertGreaterEqual(observation["recovery_count"], 1)
        self.assertTrue(observation["recovered"])
        self.assertEqual(observation["phase"], "completed")
        self.assertNotIn("do-not-return", repr(observation))
        self.assertNotIn("payload", observation)

    def test_cancel_requested_phase_is_queryable_over_http(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            service = AgentService(state_db_path=path)
            run_id = "m67-cancelling-run"
            payload = {
                "request": "取消前 secret=hidden",
                "session_id": "m67-cancel",
                "planner": "rule",
                "backend": "memory",
                "run_id": run_id,
            }
            store = service._state_store
            store.create_async_job("m67-cancel-key", run_id, payload)
            store.save(
                AgentRunResult(
                    run_id=run_id,
                    status=RunStatus.PLANNING,
                    request=payload["request"],
                    session_id=payload["session_id"],
                )
            )
            store.request_cancel(run_id)

            class TestHandler(AgentApiHandler):
                pass

            TestHandler.service = service
            server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = HTTPConnection(
                    "127.0.0.1", server.server_address[1], timeout=5
                )
                try:
                    connection.request("GET", "/runs/" + run_id + "/async")
                    response = connection.getresponse()
                    body = json.loads(response.read().decode("utf-8"))
                finally:
                    connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service._async_executor.shutdown(wait=True)

        self.assertEqual(response.status, 200)
        self.assertEqual(body["status"], "CANCEL_REQUESTED")
        self.assertEqual(body["phase"], "cancelling")
        self.assertTrue(body["cancel_requested"])
        self.assertEqual(body["last_event"], "cancel_requested")
        self.assertNotIn("hidden", repr(body))

    def test_memory_mode_keeps_the_same_async_metrics_shape(self):
        service = AgentService()
        try:
            submitted = service.run_async(
                request="你好",
                session_id="m67-memory-metrics",
                planner="rule",
                backend="memory",
            )
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                if service.get_async_observability(submitted["run_id"])["status"] == "COMPLETED":
                    break
                time.sleep(0.01)
            metrics = service.metrics()
        finally:
            service._async_executor.shutdown(wait=True)

        self.assertEqual(metrics["async_jobs"]["count"], 1)
        self.assertEqual(metrics["async_jobs"]["status_counts"]["COMPLETED"], 1)
        self.assertGreaterEqual(metrics["async_jobs"]["run_duration_ms"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
