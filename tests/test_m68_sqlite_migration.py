import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent.sqlite_store import SQLiteStateStore


_LIFECYCLE_COLUMNS = (
    "created_at",
    "started_at",
    "finished_at",
    "queue_wait_ms",
    "run_duration_ms",
    "failure_category",
    "recovery_count",
    "cancel_requested_at",
    "last_event",
)


def _initialize_legacy_database(path):
    """Create the pre-observability async_jobs schema and one old job."""
    payload = {
        "request": "查询旧库作业",
        "session_id": "m68-legacy-session",
        "planner": "rule",
        "backend": "memory",
    }
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE async_jobs (
                    idempotency_key TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner_pid INTEGER,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO async_jobs
                    (idempotency_key, run_id, payload, status, owner_pid, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-key",
                    "legacy-run",
                    json.dumps(payload, ensure_ascii=True),
                    "QUEUED",
                    None,
                    "2026-08-10 00:00:00",
                ),
            )
    finally:
        connection.close()


def _table_info(path):
    connection = sqlite3.connect(path)
    try:
        return connection.execute("PRAGMA table_info(async_jobs)").fetchall()
    finally:
        connection.close()


class M68SQLiteMigrationTests(unittest.TestCase):
    def test_legacy_job_is_readable_with_lifecycle_defaults_after_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "legacy.db")
            _initialize_legacy_database(path)

            store = SQLiteStateStore(path)
            job = store.get_async_job("legacy-run")

        self.assertEqual(job["idempotency_key"], "legacy-key")
        self.assertEqual(job["run_id"], "legacy-run")
        self.assertEqual(job["status"], "QUEUED")
        self.assertEqual(job["payload"]["session_id"], "m68-legacy-session")
        self.assertIsNone(job["created_at"])
        self.assertIsNone(job["started_at"])
        self.assertIsNone(job["finished_at"])
        self.assertIsNone(job["queue_wait_ms"])
        self.assertIsNone(job["run_duration_ms"])
        self.assertIsNone(job["failure_category"])
        self.assertEqual(job["recovery_count"], 0)
        self.assertIsNone(job["cancel_requested_at"])
        self.assertEqual(job["last_event"], "legacy")

    def test_migration_adds_each_lifecycle_column_and_recovery_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "legacy.db")
            _initialize_legacy_database(path)

            SQLiteStateStore(path)
            columns = _table_info(path)

        column_names = [row[1] for row in columns]
        self.assertEqual(column_names[-len(_LIFECYCLE_COLUMNS):], list(_LIFECYCLE_COLUMNS))
        recovery_column = next(row for row in columns if row[1] == "recovery_count")
        self.assertEqual(recovery_column[4], "0")
        self.assertEqual(recovery_column[3], 1)

    def test_repeated_store_initialization_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "legacy.db")
            _initialize_legacy_database(path)

            first = SQLiteStateStore(path)
            first_schema = _table_info(path)
            first_job = first.get_async_job("legacy-run")

            second = SQLiteStateStore(path)
            second_schema = _table_info(path)
            second_job = second.get_async_job("legacy-run")

        self.assertEqual(second_schema, first_schema)
        self.assertEqual(second_job, first_job)
        self.assertEqual(
            [row[1] for row in second_schema].count("last_event"), 1
        )

    def test_migrated_store_can_create_claim_and_complete_new_job(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "legacy.db")
            _initialize_legacy_database(path)
            store = SQLiteStateStore(path)

            created = store.create_async_job(
                "new-key",
                "new-run",
                {
                    "request": "迁移后作业",
                    "session_id": "m68-new-session",
                    "planner": "rule",
                    "backend": "memory",
                },
            )
            owner_pid = os.getpid()
            claimed = store.claim_async_job("new-run", owner_pid)
            running = store.get_async_job("new-run")
            store.finish_async_job("new-run", "COMPLETED", owner_pid)
            completed = store.get_async_job("new-run")

        self.assertTrue(created["created"])
        self.assertEqual(created["status"], "QUEUED")
        self.assertIsNotNone(created["created_at"])
        self.assertEqual(created["recovery_count"], 0)
        self.assertEqual(created["last_event"], "submitted")
        self.assertTrue(claimed)
        self.assertEqual(running["status"], "RUNNING")
        self.assertIsNotNone(running["started_at"])
        self.assertIsNotNone(running["queue_wait_ms"])
        self.assertEqual(running["last_event"], "started")
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertIsNotNone(completed["finished_at"])
        self.assertIsNotNone(completed["run_duration_ms"])
        self.assertIsNone(completed["failure_category"])
        self.assertEqual(completed["last_event"], "completed")


if __name__ == "__main__":
    unittest.main()
