import unittest

from agent.application.sessions import SessionApplication


class _SessionState:
    persistent = False

    def __init__(self):
        self.calls = []

    def list_session_runs(self, session_id, limit=20, domain_id=None):
        self.calls.append(("runs", session_id, limit, domain_id))
        return [{"run_id": "run-1", "session_id": session_id}]

    def list_sessions(self, limit=50):
        self.calls.append(("list", limit))
        return [{"session_id": "conversation-1", "display_name": "对话1"}]

    def create_session(self):
        self.calls.append(("create",))
        return {"session_id": "conversation-2", "display_name": "对话2"}

    def clear_session(self, session_id):
        self.calls.append(("clear", session_id))
        return 1

    def delete_session(self, session_id):
        self.calls.append(("delete", session_id))
        return True, 1


class M254ApplicationTests(unittest.TestCase):
    def test_session_application_owns_public_session_shapes(self):
        state = _SessionState()
        application = SessionApplication(state=state, domain_id=lambda: "gis")

        self.assertEqual(application.list_sessions(), {
            "sessions": [{"session_id": "conversation-1", "display_name": "对话1"}]
        })
        self.assertEqual(application.create_session()["display_name"], "对话2")
        self.assertEqual(application.clear_session("conversation-1")["cleared_runs"], 1)
        self.assertTrue(application.delete_session("conversation-1")["deleted"])

    def test_session_application_rejects_empty_session_id(self):
        application = SessionApplication(state=_SessionState(), domain_id=lambda: "gis")
        with self.assertRaises(ValueError):
            application.clear_session(" ")


if __name__ == "__main__":
    unittest.main()
