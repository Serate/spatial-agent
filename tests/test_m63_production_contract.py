import unittest
from unittest.mock import patch


class M63ProductionContractTests(unittest.TestCase):
    def test_sync_run_route_does_not_forward_async_idempotency_argument(self):
        try:
            import production_api
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                self.skipTest("requires production FastAPI dependencies")
            raise

        captured = {}

        class FakeService:
            def run(self, **kwargs):
                captured.update(kwargs)
                return {"status": "COMPLETED", "result_type": "direct_answer"}

        with patch.object(production_api, "service", FakeService()):
            result = production_api.run({
                "request": "你好",
                "idempotency_key": "async-only-field",
            })

        self.assertEqual(result["status"], "COMPLETED")
        self.assertNotIn("idempotency_key", captured)


if __name__ == "__main__":
    unittest.main()
