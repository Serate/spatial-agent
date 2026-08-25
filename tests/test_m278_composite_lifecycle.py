import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from agent.composite_contract import build_composite_result_contract
from agent.application.composite_runs import CompositeRunApplication
from agent.models import AgentRunResult, RunStatus
from agent.sqlite_store import SQLiteStateStore


def _request():
    return {
        "schema_version": "spatial-agent.composite-request.v1",
        "request": "组合查询空间和指标结果",
        "components": [
            {
                "component_id": "space",
                "domain_id": "gis",
                "request": "查询空间摘要",
                "planner": "rule",
                "backend": "memory",
            },
        ],
    }


def _result():
    return build_composite_result_contract(
        _request(),
        {
            "space": {
                "domain_id": "gis",
                "status": "COMPLETED",
                "result": {
                    "type": "raster_metadata_result",
                    "data_profile": {"primary": "raster", "kinds": ["raster"]},
                    "views": {"panels": {}},
                },
            }
        },
        run_id="composite-roundtrip",
    )


class _Coordinator:
    def __init__(self):
        self.calls = []

    def run(self, request, *, session_id, run_id=None):
        self.calls.append((request["request"], session_id, run_id))
        result = build_composite_result_contract(
            request,
            {
                "space": {
                    "domain_id": "gis",
                    "status": "COMPLETED",
                    "result": {
                        "type": "raster_metadata_result",
                        "data_profile": {
                            "primary": "raster",
                            "kinds": ["raster"],
                        },
                        "views": {"panels": {}},
                    },
                }
            },
            run_id=run_id,
        )
        effective_run_id = run_id or (
            "composite-"
            + result["composite"]["request"]["fingerprint"].split(":", 1)[-1][:24]
        )
        state = result["composite"]["state"]
        status = {
            "completed": "COMPLETED",
            "partial": "PARTIAL",
            "blocked": "BLOCKED",
            "failed": "FAILED",
        }[state]
        return {
            "schema_version": "spatial-agent.composite-coordinator.v1",
            "run_id": effective_run_id,
            "status": status,
            "state": state,
            "request_fingerprint": result["composite"]["request"]["fingerprint"],
            "components": result["composite"]["components"],
            "result": result,
        }


class M278CompositeEnvelopeTests(unittest.TestCase):
    def test_composite_result_survives_sqlite_roundtrip(self):
        result = AgentRunResult(
            run_id="composite-roundtrip",
            status=RunStatus.COMPLETED,
            request="组合查询空间和指标结果",
            session_id="session-1",
            domain_id="composite",
            result=_result(),
        )

        with tempfile.TemporaryDirectory() as root:
            store = SQLiteStateStore(
                str(Path(root) / "runs.db"), legacy_domain_id="composite"
            )
            store.save(result)
            restored = store.get("composite-roundtrip", domain_id="composite")

        self.assertIsNotNone(restored)
        self.assertEqual(restored.result["type"], "composite_result")
        self.assertEqual(
            restored.result["composite"]["request"]["fingerprint"],
            result.result["composite"]["request"]["fingerprint"],
        )


class M278CompositeRunApplicationTests(unittest.TestCase):
    def test_sync_result_is_queryable_and_async_submission_is_idempotent(self):
        coordinator = _Coordinator()
        request = _request()
        with tempfile.TemporaryDirectory() as root:
            db = str(Path(root) / "runs.db")
            app = CompositeRunApplication(
                coordinator=coordinator,
                state_db_path=db,
                artifact_root=str(Path(root) / "artifacts"),
                worker_count=1,
            )
            try:
                sync = app.run(request, session_id="session-1", export_artifact=True)
                detail = app.get_run(sync["run_id"])
                self.assertEqual(detail["result"]["type"], "composite_result")

                first = app.submit_async(
                    request,
                    session_id="session-1",
                    idempotency_key="same-composite",
                    export_artifact=True,
                )
                second = app.submit_async(
                    request,
                    session_id="session-1",
                    idempotency_key="same-composite",
                    export_artifact=True,
                )
                self.assertEqual(first["run_id"], second["run_id"])
                self.assertTrue(second["reused"])
                deadline = time.time() + 3
                observation = None
                while time.time() < deadline:
                    observation = app.get_observability(first["run_id"])
                    if observation["status"] == "COMPLETED":
                        break
                    time.sleep(0.01)
                self.assertIsNotNone(observation)
                self.assertEqual(observation["status"], "COMPLETED")
                self.assertEqual(len(coordinator.calls), 2)
            finally:
                app.close()

    def test_artifact_recovers_composite_result_without_sqlite_snapshot(self):
        coordinator = _Coordinator()
        request = _request()
        with tempfile.TemporaryDirectory() as root:
            artifact_root = str(Path(root) / "artifacts")
            db = str(Path(root) / "runs.db")
            app = CompositeRunApplication(
                coordinator=coordinator,
                state_db_path=db,
                artifact_root=artifact_root,
                worker_count=1,
            )
            try:
                response = app.run(request, session_id="session-1", export_artifact=True)
                run_id = response["run_id"]
            finally:
                app.close()

            recovered = CompositeRunApplication(
                coordinator=_Coordinator(),
                state_db_path=str(Path(root) / "missing.db"),
                artifact_root=artifact_root,
                worker_count=1,
            )
            try:
                detail = recovered.get_run(run_id)
                self.assertEqual(detail["result"]["type"], "composite_result")
                self.assertTrue(detail["artifact_recovered"])
            finally:
                recovered.close()

    def test_restart_claims_orphan_once_and_preserves_composite_result(self):
        coordinator = _Coordinator()
        request = _request()
        with tempfile.TemporaryDirectory() as root:
            db = str(Path(root) / "runs.db")
            artifact_root = str(Path(root) / "artifacts")
            first = CompositeRunApplication(
                coordinator=coordinator,
                state_db_path=db,
                artifact_root=artifact_root,
                worker_count=1,
            )
            try:
                # Create a durable claimed job without executing it. This is
                # the state left behind when the owning process disappears.
                first._async._schedule = lambda _payload: None
                submitted = first.submit_async(
                    request,
                    session_id="restart-session",
                    idempotency_key="restart-idem",
                )
                run_id = submitted["run_id"]
            finally:
                first.close()

            with sqlite3.connect(db) as connection:
                connection.execute(
                    "UPDATE async_jobs SET owner_pid = ?, status = 'RUNNING' "
                    "WHERE run_id = ?",
                    (999999, run_id),
                )

            recovered_coordinator = _Coordinator()
            recovered = CompositeRunApplication(
                coordinator=recovered_coordinator,
                state_db_path=db,
                artifact_root=artifact_root,
                worker_count=1,
            )
            try:
                deadline = time.time() + 3
                observation = None
                detail = None
                while time.time() < deadline:
                    observation = recovered.get_observability(run_id)
                    if observation["status"] == "COMPLETED":
                        detail = recovered.get_run(run_id)
                        break
                    time.sleep(0.01)

                self.assertIsNotNone(detail)
                self.assertEqual(detail["result"]["type"], "composite_result")
                self.assertEqual(observation["status"], "COMPLETED")
                self.assertTrue(observation["recovered"])
                self.assertEqual(observation["recovery_count"], 1)
                self.assertEqual(len(recovered_coordinator.calls), 1)
                self.assertEqual(recovered.recover(), 0)
            finally:
                recovered.close()


if __name__ == "__main__":
    unittest.main()
