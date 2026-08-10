import unittest

from agent.service import AgentService


class M68MemorySessionTests(unittest.TestCase):
    def test_memory_sessions_can_be_created_listed_and_restored(self):
        service = AgentService()
        try:
            first = service.create_session()
            second = service.create_session()
            service.run("你好", session_id=first["session_id"])

            sessions = service.list_sessions()["sessions"]
            history = service.list_session_runs(first["session_id"])["runs"]
        finally:
            service._async_executor.shutdown(wait=True)

        self.assertEqual(first["display_name"], "对话1")
        self.assertEqual(second["display_name"], "对话2")
        self.assertEqual({item["session_id"] for item in sessions}, {
            first["session_id"], second["session_id"]
        })
        self.assertEqual(history[0]["request"], "你好")
        self.assertEqual(history[0]["status"], "COMPLETED")

    def test_memory_session_clear_and_delete_remove_history(self):
        service = AgentService()
        try:
            session = service.create_session()
            service.run("你好", session_id=session["session_id"])
            cleared = service.clear_session(session["session_id"])
            deleted = service.delete_session(session["session_id"])
        finally:
            service._async_executor.shutdown(wait=True)

        self.assertEqual(cleared["cleared_runs"], 1)
        self.assertEqual(service.list_session_runs(session["session_id"])["runs"], [])
        self.assertTrue(deleted["deleted"])
        self.assertNotIn(
            session["session_id"],
            {item["session_id"] for item in service.list_sessions()["sessions"]},
        )


if __name__ == "__main__":
    unittest.main()
