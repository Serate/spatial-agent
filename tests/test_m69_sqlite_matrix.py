import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.models import AgentRunResult, RunStatus
from agent.service import AgentService
from agent.sqlite_store import SQLiteStateStore


_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT", "REJECTED", "NEEDS_CLARIFICATION"}


def _wait_for_terminal(service, run_id, timeout=8.0):
    deadline = time.monotonic() + timeout
    snapshot = None
    while time.monotonic() < deadline:
        snapshot = service.get_run(run_id)
        if snapshot.get("status") in _TERMINAL:
            return snapshot
        time.sleep(0.02)
    raise AssertionError("async run did not reach terminal state: {!r}".format(snapshot))


def _submit_from_worker(db_path, result_queue):
    service = AgentService(state_db_path=db_path)
    try:
        submitted = service.run_async(
            request="你好",
            session_id="m69-multi-worker",
            planner="rule",
            backend="memory",
            idempotency_key="m69-shared-key",
        )
        terminal = _wait_for_terminal(service, submitted["run_id"])
        result_queue.put({"submitted": submitted, "terminal": terminal})
    except Exception as exc:
        result_queue.put({"error": repr(exc)})
        raise
    finally:
        service._async_executor.shutdown(wait=True)


def _seed_recoverable_job(path, run_id, *, cancel=False, timeout_seconds=None):
    payload = {
        "request": "查询DEM栅格元数据" if timeout_seconds is not None else "你好",
        "session_id": "m69-recovery",
        "planner": "rule",
        "backend": "memory",
        "export_artifact": False,
        "export_geojson": False,
        "geojson_max_features": 100,
        "timeout_seconds": timeout_seconds,
        "spatial_context": None,
        "run_id": run_id,
    }
    store = SQLiteStateStore(path)
    store.create_async_job("m69-key-" + run_id, run_id, payload)
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
    if cancel:
        store.request_cancel(run_id)


class M69SQLiteMatrixTests(unittest.TestCase):
    def test_three_workers_share_one_idempotent_submission(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "state.db")
            queue = context.Queue()
            workers = [
                context.Process(target=_submit_from_worker, args=(db_path, queue))
                for _ in range(3)
            ]
            for worker in workers:
                worker.start()
            records = [queue.get(timeout=20) for _ in workers]
            for worker in workers:
                worker.join(timeout=20)

        self.assertTrue(all(worker.exitcode == 0 for worker in workers))
        self.assertFalse([item for item in records if "error" in item], records)
        self.assertEqual(len({item["submitted"]["run_id"] for item in records}), 1)
        self.assertEqual(sum(not item["submitted"]["idempotent"] for item in records), 1)
        self.assertTrue(all(item["terminal"]["status"] == "COMPLETED" for item in records))

    def test_sqlite_timeout_is_terminal_and_replayable_after_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            try:
                submitted = service.run_async(
                    request="查询DEM栅格元数据",
                    session_id="m69-timeout",
                    planner="rule",
                    backend="memory",
                    timeout_seconds=1e-9,
                    idempotency_key="m69-timeout-key",
                )
                result = _wait_for_terminal(service, submitted["run_id"])
                job = service._state_store.get_async_job(submitted["run_id"])
                replay = service.run_async(
                    request="不同请求",
                    session_id="other",
                    planner="rule",
                    backend="memory",
                    timeout_seconds=1e-9,
                    idempotency_key="m69-timeout-key",
                )
            finally:
                service._async_executor.shutdown(wait=True)

        self.assertEqual(result["status"], "TIMED_OUT")
        self.assertEqual(job["status"], "TIMED_OUT")
        self.assertEqual(job["failure_category"], "timeout")
        self.assertTrue(replay["idempotent"])
        self.assertEqual(replay["status"], "TIMED_OUT")

    def test_cancelled_job_is_recovered_after_worker_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            _seed_recoverable_job(path, "m69-cancel-recovery", cancel=True)
            with patch("agent.service._process_is_alive", return_value=False):
                service = AgentService(state_db_path=path)
            try:
                result = _wait_for_terminal(service, "m69-cancel-recovery")
                job = service._state_store.get_async_job("m69-cancel-recovery")
                observation = service.get_async_observability("m69-cancel-recovery")
            finally:
                service._async_executor.shutdown(wait=True)

        self.assertEqual(result["status"], "CANCELLED")
        self.assertEqual(job["status"], "CANCELLED")
        self.assertGreaterEqual(job["recovery_count"], 1)
        self.assertEqual(observation["failure_category"], "cancelled")

    def test_timed_out_job_is_recovered_after_worker_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            _seed_recoverable_job(path, "m69-timeout-recovery", timeout_seconds=1e-9)
            with patch("agent.service._process_is_alive", return_value=False):
                service = AgentService(state_db_path=path)
            try:
                result = _wait_for_terminal(service, "m69-timeout-recovery")
                job = service._state_store.get_async_job("m69-timeout-recovery")
            finally:
                service._async_executor.shutdown(wait=True)

        self.assertEqual(result["status"], "TIMED_OUT")
        self.assertEqual(job["status"], "TIMED_OUT")
        self.assertGreaterEqual(job["recovery_count"], 1)

    def test_rolling_restart_replays_terminal_result_by_request_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            first_service = AgentService(state_db_path=path)
            first = first_service.run_async(
                request="你好",
                session_id="m69-rolling-restart",
                planner="rule",
                backend="memory",
            )
            first_result = _wait_for_terminal(first_service, first["run_id"])
            first_service._async_executor.shutdown(wait=True)

            second_service = AgentService(state_db_path=path)
            try:
                replay = second_service.run_async(
                    request="你好",
                    session_id="m69-rolling-restart",
                    planner="rule",
                    backend="memory",
                )
                restored = second_service.get_run(first["run_id"])
            finally:
                second_service._async_executor.shutdown(wait=True)

        self.assertEqual(first_result["status"], "COMPLETED")
        self.assertTrue(replay["idempotent"])
        self.assertEqual(replay["run_id"], first["run_id"])
        self.assertEqual(restored["status"], "COMPLETED")
        self.assertEqual(restored["answer"], first_result["answer"])


if __name__ == "__main__":
    unittest.main()
