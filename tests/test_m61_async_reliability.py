import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from agent.models import AgentRunResult, RunStatus
from agent.service import AgentService
from agent.sqlite_store import SQLiteStateStore


def _wait_for_terminal(service, run_id, timeout=3.0):
    deadline = time.monotonic() + timeout
    snapshot = None
    while time.monotonic() < deadline:
        try:
            snapshot = service.get_run(run_id)
        except ValueError:
            pass
        if snapshot and snapshot["status"] not in {"PLANNING", "EXECUTING"}:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("async run did not reach a terminal state: {}".format(snapshot))


def _wait_for_job_terminal(service, run_id, timeout=3.0):
    deadline = time.monotonic() + timeout
    job = None
    while time.monotonic() < deadline:
        job = service._state_store.get_async_job(run_id)
        if job and job["status"] not in {"QUEUED", "RUNNING"}:
            return job
        time.sleep(0.01)
    raise AssertionError("async job did not reach a terminal state: {}".format(job))


class M61AsyncReliabilityTests(unittest.TestCase):
    def test_concurrent_duplicate_submissions_share_one_run_id(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            submit = lambda: service.run_async(
                request="你好",
                session_id="duplicate-post",
                planner="rule",
                backend="memory",
            )
            with ThreadPoolExecutor(max_workers=5) as executor:
                responses = list(executor.map(lambda _: submit(), range(5)))

            run_ids = {item["run_id"] for item in responses}
            self.assertEqual(len(run_ids), 1)
            self.assertEqual(sum(not item["idempotent"] for item in responses), 1)
            _wait_for_terminal(service, responses[0]["run_id"])
            self.assertEqual(
                len(service.list_session_runs("duplicate-post")["runs"]), 1
            )

    def test_explicit_run_id_is_idempotent_even_after_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            first = service.run_async(
                request="你好",
                session_id="explicit-id",
                run_id="m61-fixed-run",
            )
            completed = _wait_for_terminal(service, first["run_id"])
            replay = service.run_async(
                request="不同请求应被幂等重放忽略",
                session_id="other-session",
                run_id="m61-fixed-run",
            )

            self.assertEqual(replay["run_id"], first["run_id"])
            self.assertEqual(replay["status"], "COMPLETED")
            self.assertTrue(replay["idempotent"])
            self.assertEqual(service.get_run(first["run_id"])["request"], "你好")
            self.assertEqual(completed["status"], "COMPLETED")
            _wait_for_job_terminal(service, first["run_id"])

    def test_new_service_reclaims_job_left_by_dead_process(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            store = SQLiteStateStore(path)
            run_id = "m61-restart-run"
            payload = {
                "request": "你好",
                "session_id": "restart-recovery",
                "planner": "rule",
                "backend": "memory",
                "export_artifact": False,
                "export_geojson": False,
                "geojson_max_features": 100,
                "timeout_seconds": None,
                "spatial_context": None,
                "run_id": run_id,
            }
            store.create_async_job("run_id:" + run_id, run_id, payload)
            store.save(
                AgentRunResult(
                    run_id=run_id,
                    status=RunStatus.PLANNING,
                    request="你好",
                    session_id="restart-recovery",
                )
            )
            with store._connection() as connection:
                connection.execute(
                    "UPDATE async_jobs SET owner_pid = 1, status = 'RUNNING' WHERE run_id = ?",
                    (run_id,),
                )

            restarted = AgentService(state_db_path=path)
            result = _wait_for_terminal(restarted, run_id)

            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(restarted._state_store.get_async_job(run_id)["status"], "COMPLETED")

    def test_unexpected_worker_exception_marks_job_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            with patch.object(service, "run", side_effect=RuntimeError("worker crashed")):
                queued = service.run_async(
                    request="你好", session_id="worker-failure", planner="rule"
                )
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    job = service._state_store.get_async_job(queued["run_id"])
                    if job and job["status"] == "FAILED":
                        break
                    time.sleep(0.01)

            self.assertEqual(
                service._state_store.get_async_job(queued["run_id"])["status"], "FAILED"
            )


if __name__ == "__main__":
    unittest.main()
