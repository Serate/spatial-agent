import tempfile
import unittest
from pathlib import Path

from agent.service import AgentService


class M48SessionLifecycleTests(unittest.TestCase):
    def test_compare_buildability_across_regions(self):
        service = AgentService()

        result = service.compare_buildability_regions(
            ["洪山区", "江夏区"], threshold=20, backend="memory"
        )

        self.assertEqual(result["slope_limit_degrees"], 20.0)
        self.assertEqual([row["admin_name"] for row in result["results"]], ["洪山区", "江夏区"])
        self.assertEqual(len(result["results"]), 2)

    def test_clear_session_removes_runs_but_keeps_session(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            service.run("你好", session_id="conversation-1")

            result = service.clear_session("conversation-1")

            self.assertEqual(result["cleared_runs"], 1)
            self.assertEqual(service.list_session_runs("conversation-1")["runs"], [])
            self.assertEqual(len(service.list_sessions()["sessions"]), 1)

    def test_delete_session_removes_session_and_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            service.run("你好", session_id="conversation-1")

            result = service.delete_session("conversation-1")

            self.assertTrue(result["deleted"])
            self.assertEqual(service.list_session_runs("conversation-1")["runs"], [])
            self.assertEqual(service.list_sessions()["sessions"], [])


if __name__ == "__main__":
    unittest.main()
