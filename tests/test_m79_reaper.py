"""M79.4.2 tests: job-level wall-clock timeout and periodic reaper.

Regression coverage for the converged ServiceState:
1. A job stuck in QUEUED/RUNNING past SPATIAL_AGENT_ASYNC_TIMEOUT_SECONDS is
   detected by expired_run_ids and marked TIMED_OUT by expire_job.
2. The reaper loop performs that sweep on its interval without killing the
   service.
3. The AgentService facade still validates planner/backend through the
   converged runtime cache (contract moved from _runtime_key into
   ServiceState.runtime).
"""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from agent.service import AgentService
from agent.service_state import ServiceState, async_timeout_seconds


class M79ReaperTests(unittest.TestCase):
    def test_timeout_seconds_env_parsing(self):
        with mock.patch.dict(
            os.environ, {"SPATIAL_AGENT_ASYNC_TIMEOUT_SECONDS": "7"}
        ):
            self.assertEqual(async_timeout_seconds(), 7.0)
        with mock.patch.dict(
            os.environ, {"SPATIAL_AGENT_ASYNC_TIMEOUT_SECONDS": "0"}
        ):
            with self.assertRaises(ValueError):
                async_timeout_seconds()

    def test_memory_expired_run_ids_detects_old_jobs(self):
        state = ServiceState(runtime_factory=lambda p, b, **kw: None)
        state.submit_memory_job(
            "key-1",
            {
                "run_id": "run-1",
                "payload": {"request": "你好", "session_id": "s"},
                "status": "QUEUED",
                "created_at": time.time() - state.timeout_seconds - 10,
                "last_event": "submitted",
            },
        )
        state.submit_memory_job(
            "key-2",
            {
                "run_id": "run-2",
                "payload": {"request": "你好", "session_id": "s"},
                "status": "RUNNING",
                "created_at": time.time() - state.timeout_seconds - 5,
                "started_at": time.time() - 5,
                "last_event": "started",
            },
        )
        state.submit_memory_job(
            "key-3",
            {
                "run_id": "run-3",
                "payload": {"request": "你好", "session_id": "s"},
                "status": "QUEUED",
                "created_at": time.time(),
                "last_event": "submitted",
            },
        )
        expired = state.expired_run_ids()
        self.assertIn("run-1", expired)
        self.assertIn("run-2", expired)
        self.assertNotIn("run-3", expired)

        state.expire_job("run-1")
        job = state.memory_job_by_run_id("run-1")
        self.assertEqual(job["status"], "TIMED_OUT")
        self.assertEqual(job["failure_category"], "timeout")

    def test_reaper_marks_expired_jobs(self):
        state = ServiceState(runtime_factory=lambda p, b, **kw: None)
        state.submit_memory_job(
            "key-old",
            {
                "run_id": "run-old",
                "payload": {"request": "你好", "session_id": "s"},
                "status": "QUEUED",
                "created_at": time.time() - state.timeout_seconds - 20,
                "last_event": "submitted",
            },
        )
        state._reaper_interval = 0.05
        state.start_reaper()
        try:
            deadline = time.time() + 3
            while time.time() < deadline:
                job = state.memory_job_by_run_id("run-old")
                if job is not None and job["status"] == "TIMED_OUT":
                    break
                time.sleep(0.02)
            job = state.memory_job_by_run_id("run-old")
            self.assertEqual(job["status"], "TIMED_OUT")
        finally:
            state.stop_reaper()

    def test_reaper_does_not_touch_fresh_jobs(self):
        state = ServiceState(runtime_factory=lambda p, b, **kw: None)
        state.submit_memory_job(
            "key-new",
            {
                "run_id": "run-new",
                "payload": {"request": "你好", "session_id": "s"},
                "status": "RUNNING",
                "created_at": time.time(),
                "started_at": time.time(),
                "last_event": "started",
            },
        )
        state._reaper_interval = 0.05
        state.start_reaper()
        try:
            time.sleep(0.2)
            job = state.memory_job_by_run_id("run-new")
            self.assertEqual(job["status"], "RUNNING")
        finally:
            state.stop_reaper()

    def test_facade_runtime_validates_planner_backend(self):
        service = AgentService()
        try:
            with self.assertRaises(ValueError):
                service._runtime("rule", "postgres")
            with self.assertRaises(ValueError):
                service._runtime("random", "memory")
        finally:
            service.close()

    def test_sqlite_reaper_expires_old_job(self):
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "state.db")
            service = AgentService(state_db_path=db)
            try:
                submitted = service.run_async(
                    request="你好", session_id="m79-reaper-sqlite"
                )
                run_id = submitted["run_id"]
                service._state.expire_job(run_id)
                job = service._state.async_job(run_id)
                self.assertEqual(job["status"], "TIMED_OUT")
            finally:
                service.close()

    def test_sqlite_reaper_expires_unclaimed_job(self):
        # A job that was created but never claimed has owner_pid NULL. The
        # owner-scoped finish would no-op; the reaper must still expose a
        # terminal TIMED_OUT status.
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "state.db")
            service = AgentService(state_db_path=db)
            try:
                from agent.models import AgentRunResult, RunStatus

                store = service._state.state_store
                run_id = "m79-unclaimed-run"
                store.create_async_job(
                    "m79-unclaimed-key", run_id,
                    {"request": "你好", "session_id": "s", "run_id": run_id},
                )
                service._state.expire_job(run_id)
                job = store.get_async_job(run_id)
                self.assertEqual(job["status"], "TIMED_OUT")
                self.assertEqual(job["failure_category"], "timeout")
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
