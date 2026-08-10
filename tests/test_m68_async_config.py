import os
import unittest
from unittest.mock import patch

from agent.service import AgentService


class M68AsyncConfigTests(unittest.TestCase):
    def test_worker_count_is_configurable_and_reported(self):
        with patch.dict(os.environ, {"SPATIAL_AGENT_ASYNC_WORKERS": "2"}):
            service = AgentService()
        try:
            self.assertEqual(service._async_worker_count, 2)
            self.assertEqual(service.metrics()["async_jobs"]["worker_count"], 2)
        finally:
            service._async_executor.shutdown(wait=True)

    def test_worker_count_defaults_to_four(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SPATIAL_AGENT_ASYNC_WORKERS", None)
            service = AgentService()
        try:
            self.assertEqual(service._async_worker_count, 4)
        finally:
            service._async_executor.shutdown(wait=True)

    def test_invalid_worker_count_fails_fast(self):
        for value in ("0", "17", "many"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"SPATIAL_AGENT_ASYNC_WORKERS": value}
            ):
                with self.assertRaisesRegex(ValueError, "SPATIAL_AGENT_ASYNC_WORKERS"):
                    AgentService()


if __name__ == "__main__":
    unittest.main()
