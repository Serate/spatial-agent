import tempfile
import unittest
from pathlib import Path

from agent.service import AgentService
from agent.sqlite_store import SQLiteConversationStore, SQLiteStateStore
from run_demo import build_runtime


class M42SQLiteStoreTests(unittest.TestCase):
    def test_clarification_survives_service_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent.db")
            first_service = AgentService(state_db_path=path)
            first = first_service.run("查询行政区边界", session_id="restart-session")

            second_service = AgentService(state_db_path=path)
            second = second_service.run("洪山区", session_id="restart-session")

        self.assertEqual(first["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(second["status"], "COMPLETED")
        self.assertIn("洪山区", second["resolved_request"])

    def test_run_snapshot_survives_runtime_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent.db")
            first_runtime = build_runtime(
                "rule",
                "memory",
                state_store=SQLiteStateStore(path),
                conversation_store=SQLiteConversationStore(path),
            )
            result = first_runtime.run("查询洪山区行政区边界", session_id="run-session")

            second_runtime = build_runtime(
                "rule",
                "memory",
                state_store=SQLiteStateStore(path),
                conversation_store=SQLiteConversationStore(path),
            )
            restored = second_runtime.get_run(result.run_id)

        self.assertIsNotNone(restored)
        self.assertEqual(restored.status.value, "COMPLETED")
        self.assertEqual(restored.answer, result.answer)
        self.assertEqual(restored.steps[1].result["first_name"], "洪山区")

    def test_sessions_are_isolated_in_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent.db")
            service = AgentService(state_db_path=path)
            first = service.run("查询行政区边界", session_id="one")
            unrelated = service.run("洪山区", session_id="two")

        self.assertEqual(first["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(unrelated["status"], "NEEDS_CLARIFICATION")

    def test_cancel_control_survives_store_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent.db")
            first_store = SQLiteStateStore(path)
            first_store.request_cancel("run-1")
            second_store = SQLiteStateStore(path)

            self.assertTrue(second_store.is_cancel_requested("run-1"))
            second_store.clear_cancel("run-1")
            self.assertFalse(first_store.is_cancel_requested("run-1"))

    def test_sqlite_run_index_and_metrics_include_non_exported_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent.db")
            service = AgentService(state_db_path=path)
            result = service.run("查询洪山区行政区边界")
            runs = service.list_runs()["runs"]
            metrics = service.metrics()

        self.assertEqual(runs[0]["run_id"], result["run_id"])
        self.assertEqual(metrics["run_count"], 1)
        self.assertEqual(metrics["status_counts"]["COMPLETED"], 1)

    def test_run_can_be_queried_after_service_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent.db")
            first = AgentService(state_db_path=path).run("查询洪山区行政区边界")
            second_service = AgentService(state_db_path=path)
            restored = second_service.get_run(first["run_id"])

        self.assertEqual(restored["run_id"], first["run_id"])
        self.assertEqual(restored["status"], "COMPLETED")
        self.assertIn("trace_summary", restored)


if __name__ == "__main__":
    unittest.main()
