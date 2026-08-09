import multiprocessing
import os
import queue
import tempfile
import time
import unittest
from pathlib import Path

from agent.models import AgentRunResult, RunStatus
from agent.service import AgentService
from agent.sqlite_store import SQLiteStateStore


TERMINAL_STATUSES = {"COMPLETED", "FAILED", "REJECTED", "CLARIFICATION_REQUIRED"}


def _wait_for_terminal(service, run_id, timeout=8.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = service.get_run(run_id)
        except ValueError:
            pass
        if last and last["status"] in TERMINAL_STATUSES:
            job = service._state_store.get_async_job(run_id)
            if job is None or job["status"] in TERMINAL_STATUSES:
                return last
        time.sleep(0.02)
    raise AssertionError("async run did not reach terminal state: {!r}".format(last))


def _submission_worker(db_path, result_queue):
    service = AgentService(state_db_path=db_path)
    try:
        response = service.run_async(
            request="查询DEM栅格元数据",
            session_id="m65-cross-worker",
            planner="rule",
            backend="memory",
            idempotency_key="m65-same-submission",
        )
        terminal = _wait_for_terminal(service, response["run_id"])
        result_queue.put({"response": response, "terminal": terminal})
    except Exception as exc:
        result_queue.put({"error": repr(exc)})
        raise
    finally:
        service._async_executor.shutdown(wait=True)


def _poll_worker(db_path, run_id, result_queue):
    service = AgentService(state_db_path=db_path)
    try:
        result_queue.put({"terminal": _wait_for_terminal(service, run_id)})
    except Exception as exc:
        result_queue.put({"error": repr(exc)})
        raise
    finally:
        service._async_executor.shutdown(wait=True)


def _claim_then_crash_worker(db_path, run_id, result_queue):
    store = SQLiteStateStore(db_path)
    claimed = store.claim_async_job(run_id, os.getpid())
    result_queue.put({"claimed": claimed, "pid": os.getpid()})
    result_queue.close()
    result_queue.join_thread()
    os._exit(0)


class M65ProductionReliabilityTests(unittest.TestCase):
    def test_multiple_workers_submit_once_and_independent_worker_can_poll(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "state.db")
            submit_queue = context.Queue()
            workers = [
                context.Process(target=_submission_worker, args=(db_path, submit_queue))
                for _ in range(2)
            ]
            for worker in workers:
                worker.start()

            records = [submit_queue.get(timeout=15) for _ in workers]
            for worker in workers:
                worker.join(timeout=15)
                self.assertEqual(worker.exitcode, 0)

            errors = [record for record in records if "error" in record]
            self.assertFalse(errors, errors)
            run_ids = {record["response"]["run_id"] for record in records}
            self.assertEqual(run_ids, {records[0]["terminal"]["run_id"]})
            self.assertEqual(sum(not record["response"]["idempotent"] for record in records), 1)
            self.assertTrue(all(record["terminal"]["status"] == "COMPLETED" for record in records))

            poll_queue = context.Queue()
            poller = context.Process(
                target=_poll_worker,
                args=(db_path, records[0]["response"]["run_id"], poll_queue),
            )
            poller.start()
            polled = poll_queue.get(timeout=15)
            poller.join(timeout=15)

            self.assertEqual(poller.exitcode, 0)
            self.assertNotIn("error", polled)
            self.assertEqual(polled["terminal"]["status"], "COMPLETED")

    def test_worker_crash_after_claim_is_recovered_by_new_worker(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "state.db")
            run_id = "m65-crashed-worker"
            payload = {
                "request": "你好",
                "session_id": "m65-crash-recovery",
                "planner": "rule",
                "backend": "memory",
                "export_artifact": False,
                "export_geojson": False,
                "geojson_max_features": 100,
                "timeout_seconds": None,
                "spatial_context": None,
                "run_id": run_id,
            }
            store = SQLiteStateStore(db_path)
            store.create_async_job("m65-crash-key", run_id, payload)
            store.save(
                AgentRunResult(
                    run_id=run_id,
                    status=RunStatus.PLANNING,
                    request="你好",
                    session_id="m65-crash-recovery",
                )
            )

            crash_queue = context.Queue()
            crashed = context.Process(
                target=_claim_then_crash_worker,
                args=(db_path, run_id, crash_queue),
            )
            crashed.start()
            claim = crash_queue.get(timeout=10)
            crashed.join(timeout=10)

            self.assertEqual(crashed.exitcode, 0)
            self.assertTrue(claim["claimed"])
            self.assertEqual(
                SQLiteStateStore(db_path).get_async_job(run_id)["status"], "RUNNING"
            )

            restarted = AgentService(state_db_path=db_path)
            try:
                recovered = _wait_for_terminal(restarted, run_id)
                job = restarted._state_store.get_async_job(run_id)
            finally:
                restarted._async_executor.shutdown(wait=True)

        self.assertEqual(recovered["status"], "COMPLETED")
        self.assertEqual(job["status"], "COMPLETED")

    def test_production_fastapi_handler_preserves_request_fingerprint_idempotency(self):
        try:
            import production_api
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                self.skipTest("requires production FastAPI dependencies")
            raise

        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            original = production_api.service
            production_api.service = service
            try:
                payload = {
                    "request": "你好",
                    "session_id": "m65-fastapi-idempotency",
                    "planner": "rule",
                    "backend": "memory",
                }
                first = production_api.run_async(payload)
                second = production_api.run_async(dict(payload))
                terminal = _wait_for_terminal(service, first["run_id"])
            finally:
                production_api.service = original
                service._async_executor.shutdown(wait=True)

        self.assertEqual(first["run_id"], second["run_id"])
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(terminal["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
