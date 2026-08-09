import tempfile
import time
import unittest
from pathlib import Path

from agent.service import AgentService


class M61AsyncIdempotencyTests(unittest.TestCase):
    def test_duplicate_sqlite_submission_reuses_run_id(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            first = service.run_async(
                request="你好",
                session_id="m61-idempotent",
                idempotency_key="same-request-1",
            )
            second = service.run_async(
                request="你好",
                session_id="m61-idempotent",
                idempotency_key="same-request-1",
            )
            self.assertEqual(first["run_id"], second["run_id"])
            self.assertTrue(second["idempotent"])
            for _ in range(50):
                result = service.get_run(first["run_id"])
                if result["status"] == "COMPLETED":
                    break
                time.sleep(0.01)
            self.assertEqual(service.get_run(first["run_id"])["status"], "COMPLETED")

    def test_idempotency_key_is_validated(self):
        service = AgentService()
        with self.assertRaises(ValueError):
            service.run_async(request="你好", idempotency_key=" ")


if __name__ == "__main__":
    unittest.main()
