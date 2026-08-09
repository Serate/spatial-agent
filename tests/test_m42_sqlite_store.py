import tempfile
import unittest
from pathlib import Path

from agent.service import AgentService
from agent.sqlite_store import SQLiteConversationStore, SQLiteStateStore
from run_demo import build_runtime


class M42SQLiteStoreTests(unittest.TestCase):
    def test_named_sessions_survive_store_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent.db")
            first_store = SQLiteConversationStore(path)
            first = first_store.create_session()
            second = first_store.create_session()
            restored = SQLiteConversationStore(path).list_sessions()

        self.assertEqual(first["display_name"], "对话1")
        self.assertEqual(second["display_name"], "对话2")
        self.assertEqual({item["display_name"] for item in restored}, {"对话1", "对话2"})

    def test_service_registers_named_session_when_it_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent.db")
            service = AgentService(state_db_path=path)
            service.run("查询洪山区行政区边界", session_id="conversation-1")
            sessions = service.list_sessions()["sessions"]

        self.assertEqual(sessions[0]["session_id"], "conversation-1")
        self.assertEqual(sessions[0]["display_name"], "对话1")

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

    def test_structured_clarification_survives_service_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent.db")
            first = AgentService(state_db_path=path).run(
                "查询武汉城市绿地空间分布", session_id="structured-clarification"
            )
            restored = AgentService(state_db_path=path).get_run(first["run_id"])

        self.assertEqual(restored["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(restored["clarification"]["state"], "unmatched_spatial_capability")

    def test_async_artifact_references_survive_polling_and_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent.db")
            first = AgentService(state_db_path=path)
            queued = first.run_async(
                request="查询洪山区行政区边界",
                session_id="async-artifact",
                export_artifact=True,
                export_geojson=True,
            )
            final = None
            for _ in range(100):
                final = first.get_run(queued["run_id"])
                if final["status"] not in {"PLANNING", "EXECUTING", "CREATED"}:
                    break
                import time
                time.sleep(0.02)
            restored = AgentService(state_db_path=path).get_run(queued["run_id"])

        self.assertEqual(final["status"], "COMPLETED")
        self.assertTrue(final.get("artifact_ref"))
        self.assertTrue(final.get("geojson_ref"))
        self.assertEqual(restored.get("geojson_ref"), final["geojson_ref"])

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

    def test_session_run_index_restores_recent_conversation_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent.db")
            service = AgentService(state_db_path=path)
            first = service.run("你好", session_id="conversation-1")
            second = service.run("查询洪山区行政区边界", session_id="conversation-2")
            same_session = service.run("查询DEM栅格元数据", session_id="conversation-1")
            records = service.list_session_runs("conversation-1")["runs"]

        self.assertEqual({item["run_id"] for item in records}, {same_session["run_id"], first["run_id"]})
        self.assertTrue(all(item["session_id"] == "conversation-1" for item in records))
        self.assertNotIn(second["run_id"], [item["run_id"] for item in records])


if __name__ == "__main__":
    unittest.main()
