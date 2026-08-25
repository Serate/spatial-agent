import time
import unittest
from threading import Event

from evaluation.live_provider_probe import run_provider_probe


class _FakeClient:
    def __init__(self, payload=None, metrics=None):
        self.payload = payload
        self._metrics = metrics or {
            "provider": "fake-provider",
            "model": "fake-model",
            "wire_api": "chat_completions",
            "status": "success",
            "attempts": 1,
            "retries": 0,
            "usage": {"total_tokens": 7},
        }

    def complete_json(self, messages, schema, *, schema_name):
        return self.payload

    def metrics(self):
        return dict(self._metrics)


class M271ProviderProbeTests(unittest.TestCase):
    def test_ready_probe_returns_safe_receipt(self):
        report = run_provider_probe(
            client_factory=lambda timeout: _FakeClient({"status": "ready"}),
            timeout_seconds=1,
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["status"], "READY")
        self.assertTrue(report["response_shape_valid"])
        self.assertEqual(report["provider"], "fake-provider")
        self.assertEqual(report["metrics"]["token_usage"]["total_tokens"], 7)
        self.assertNotIn("messages", report)

    def test_invalid_shape_and_provider_error_are_bounded_and_redacted(self):
        invalid = run_provider_probe(
            client_factory=lambda timeout: _FakeClient(
                {"status": "ready", "secret": "not-public"}
            ),
            timeout_seconds=1,
        )
        self.assertFalse(invalid["passed"])
        self.assertEqual(invalid["error_class"], "invalid_response")
        self.assertNotIn("not-public", repr(invalid))

        def failing(timeout):
            raise TimeoutError("provider key and raw response must not escape")

        failed = run_provider_probe(client_factory=failing, timeout_seconds=1)
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["error_class"], "timeout")
        self.assertNotIn("provider key", repr(failed))

    def test_blocking_client_returns_timeout_before_worker_finishes(self):
        blocked = Event()

        class BlockingClient:
            def complete_json(self, messages, schema, *, schema_name):
                blocked.wait()

            def metrics(self):
                return {"provider": "blocked", "model": "blocked", "status": "in_progress"}

        started = time.monotonic()
        report = run_provider_probe(
            client_factory=lambda timeout: BlockingClient(),
            timeout_seconds=0.05,
        )

        self.assertLess(time.monotonic() - started, 0.5)
        self.assertFalse(report["passed"])
        self.assertEqual(report["error_class"], "timeout")

    def test_non_positive_timeout_is_rejected(self):
        with self.assertRaises(ValueError):
            run_provider_probe(client_factory=lambda timeout: _FakeClient(), timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
