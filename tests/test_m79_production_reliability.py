"""M79 production reliability: regression tests for issues found by the real
container acceptance chain.

Two production defects were caught only when Docker was actually running:
1. A duplicate memory-mode async submission deadlocked forever because the
   response builder re-acquired the non-reentrant _async_lock while it was
   already held (run_async returned inside the lock).
2. The production container ran in memory mode (no SPATIAL_AGENT_STATE_DB), so
   two Uvicorn workers could not see each other's jobs: duplicate submissions
   were not idempotent and polling returned 404.
"""

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from agent.service import AgentService


class M79ProductionReliabilityTests(unittest.TestCase):
    def test_memory_duplicate_submission_does_not_deadlock(self):
        # Regression: the second submission used to hang forever on the
        # non-reentrant lock. Guarded by a watchdog so a regression fails the
        # test instead of hanging the suite.
        service = AgentService()
        first = service.run_async(request="你好", session_id="m79-mem-duplicate")
        outcome = {}

        def submit():
            try:
                outcome["result"] = service.run_async(
                    request="你好", session_id="m79-mem-duplicate"
                )
            except Exception as exc:  # pragma: no cover - regression path
                outcome["error"] = exc

        thread = threading.Thread(target=submit)
        thread.start()
        thread.join(timeout=10)
        if thread.is_alive():  # pragma: no cover - deadlock regression
            self.fail("memory-mode duplicate async submission deadlocked")
        self.assertNotIn("error", outcome)
        second = outcome["result"]
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertTrue(second["idempotent"])

    def test_state_db_env_selects_sqlite_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "state.db")
            with mock.patch.dict(os.environ, {"SPATIAL_AGENT_STATE_DB": db}):
                service = AgentService()
                self.assertIsNotNone(service._state_store)
                self.assertIsNotNone(service._conversation_store)
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("SPATIAL_AGENT_STATE_DB", None)
                memory_service = AgentService()
                self.assertIsNone(memory_service._state_store)

    def test_sqlite_run_is_visible_across_service_instances(self):
        # Multi-worker equivalent: each Uvicorn worker owns a memory-mode
        # service; only the shared SQLite store makes jobs and results visible
        # across workers.
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "state.db")
            first = AgentService(state_db_path=db)
            try:
                queued = first.run_async(request="你好", session_id="m79-cross-worker")
                for _ in range(100):
                    result = first.get_run(queued["run_id"])
                    if result["status"] == "COMPLETED":
                        break
                    time.sleep(0.01)
                self.assertEqual(first.get_run(queued["run_id"])["status"], "COMPLETED")

                second = AgentService(state_db_path=db)
                try:
                    restored = second.get_run(queued["run_id"])
                    self.assertEqual(restored["run_id"], queued["run_id"])
                    self.assertEqual(restored["status"], "COMPLETED")
                finally:
                    second.close()
            finally:
                first.close()

    def test_sqlite_duplicate_submission_is_idempotent_across_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "state.db")
            first = AgentService(state_db_path=db)
            second = AgentService(state_db_path=db)
            try:
                submitted = first.run_async(request="你好", session_id="m79-cross-idem")
                duplicate = second.run_async(request="你好", session_id="m79-cross-idem")
                self.assertEqual(submitted["run_id"], duplicate["run_id"])
                self.assertTrue(duplicate["idempotent"])
            finally:
                second.close()
                first.close()

    def test_dockerfile_sets_production_sqlite_state_db(self):
        # Config contract: the production image must run SQLite mode so its two
        # Uvicorn workers share run snapshots. This regression was introduced
        # when the env var was dropped, silently switching the container to
        # memory mode.
        dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text(
            encoding="utf-8"
        )
        self.assertIn("SPATIAL_AGENT_STATE_DB=/app/outputs/spatial-agent.db", dockerfile)
        self.assertIn("uvicorn", dockerfile)
        self.assertIn("--workers", dockerfile)

    def test_container_config_template_includes_full_demo_datasets(self):
        # M79.4 config contract: the production container config must expose the
        # analysis-ready aligned layers and roads/water so buildability,
        # constrained buildability, and region comparison are demonstrable in
        # the container instead of failing the alignment/data gate.
        import json

        path = (
            Path(__file__).parents[1]
            / "config"
            / "datasets.container.example.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        datasets = payload.get("datasets") or {}
        self.assertIn("admin_areas", datasets)
        self.assertIn("roads", datasets)
        self.assertIn("water", datasets)
        self.assertIn("analysis-ready", str(datasets.get("dem", {}).get("path", "")))
        self.assertIn("analysis-ready", str(datasets.get("land_use", {}).get("path", "")))
        self.assertEqual(datasets.get("roads", {}).get("path"), "wuhan-osm.gpkg")
        self.assertEqual(datasets.get("water", {}).get("path"), "wuhan-osm.gpkg")
        analysis_ready = payload.get("analysis_ready") or {}
        self.assertTrue(analysis_ready.get("required", False))
        self.assertIn("/data/analysis-ready", str(analysis_ready.get("report", "")))


if __name__ == "__main__":
    unittest.main()
