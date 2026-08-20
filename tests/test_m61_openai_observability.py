import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from agent.errors import PlanningError
from agent.llm_planner import OpenAIPlannerClient
from agent.openai_config import load_openai_config


class _Response:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        return False

    def read(self):
        return self._payload


def _success_response():
    return _Response(
        {
            "choices": [{"message": {"content": '{"goal":"ok"}'}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        }
    )


class M61OpenAIObservabilityTests(unittest.TestCase):
    def test_config_loads_retry_settings_and_env_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "openai.local.json"
            path.write_text(
                json.dumps(
                    {
                        "max_retries": 1,
                        "retry_backoff_seconds": 0.25,
                        "retry_backoff_max_seconds": 2,
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"OPENAI_MAX_RETRIES": "3"}, clear=True):
                config = load_openai_config(str(path))

        self.assertEqual(config["max_retries"], 3)
        self.assertEqual(config["retry_backoff_seconds"], 0.25)
        self.assertEqual(config["retry_backoff_max_seconds"], 2.0)

    def test_retries_transient_http_failure_and_records_safe_metrics(self):
        client = OpenAIPlannerClient(
            api_key="sk-secret",
            wire_api="chat_completions",
            max_retries=1,
            retry_backoff_seconds=0.1,
            retry_backoff_max_seconds=1,
            timeout_seconds=4,
        )
        transient = urllib.error.HTTPError(
            "https://example.test", 503, "temporarily unavailable", {}, io.BytesIO(b"secret")
        )
        with patch("agent.llm_planner.urllib.request.urlopen", side_effect=[transient, _success_response()]) as call, \
             patch("agent.llm_planner.time.sleep") as sleep:
            self.assertEqual(client.complete_json([], {}), {"goal": "ok"})

        self.assertEqual(call.call_count, 2)
        sleep.assert_called_once_with(0.1)
        metrics = client.metrics()
        self.assertEqual(metrics["status"], "success")
        self.assertEqual(metrics["attempts"], 2)
        self.assertEqual(metrics["retries"], 1)
        self.assertGreaterEqual(metrics["latency_ms"], 0)
        self.assertEqual(metrics["usage"]["total_tokens"], 16)
        self.assertNotIn("api_key", metrics)
        self.assertNotIn("sk-secret", repr(metrics))
        self.assertNotIn("secret", repr(metrics))

    def test_permission_denied_url_error_is_not_retried(self):
        client = OpenAIPlannerClient(
            api_key="sk-test",
            wire_api="chat_completions",
            max_retries=3,
            retry_backoff_seconds=0.1,
        )
        error = urllib.error.URLError(PermissionError(10013, "socket denied"))
        with patch("agent.llm_planner.urllib.request.urlopen", side_effect=error) as call, \
             patch("agent.llm_planner.time.sleep") as sleep:
            with self.assertRaises(PlanningError):
                client.complete_json([], {})

        call.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(client.metrics()["error_type"], "url_error")
        self.assertEqual(client.metrics()["attempts"], 1)

    def test_timeout_retries_when_configured_and_zero_disables_retry(self):
        retrying = OpenAIPlannerClient(
            api_key="sk-test",
            wire_api="chat_completions",
            max_retries=1,
            retry_backoff_seconds=0,
        )
        with patch(
            "agent.llm_planner.urllib.request.urlopen",
            side_effect=[TimeoutError(), _success_response()],
        ) as call:
            self.assertEqual(retrying.complete_json([], {}), {"goal": "ok"})
        self.assertEqual(call.call_count, 2)
        self.assertEqual(retrying.metrics()["attempts"], 2)

        single = OpenAIPlannerClient(
            api_key="sk-test", wire_api="chat_completions", max_retries=0
        )
        with patch(
            "agent.llm_planner.urllib.request.urlopen", side_effect=TimeoutError()
        ) as call:
            with self.assertRaises(PlanningError):
                single.complete_json([], {})
        call.assert_called_once()
        self.assertEqual(single.metrics()["error_type"], "timeout")

    def test_invalid_observability_settings_are_rejected(self):
        with self.assertRaises(PlanningError):
            OpenAIPlannerClient(api_key="sk-test", max_retries=-1)
        with self.assertRaises(PlanningError):
            OpenAIPlannerClient(
                api_key="sk-test", retry_backoff_seconds=2, retry_backoff_max_seconds=1
            )

    def test_client_does_not_retry_authentication_failure(self):
        client = OpenAIPlannerClient(
            api_key="sk-test", wire_api="chat_completions", max_retries=3
        )
        error = urllib.error.HTTPError(
            "https://example.test", 401, "unauthorized", {}, io.BytesIO(b"nope")
        )
        with patch("agent.llm_planner.urllib.request.urlopen", side_effect=error) as call, \
             patch("agent.llm_planner.time.sleep") as sleep:
            with self.assertRaises(PlanningError):
                client.complete_json([], {})

        call.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(client.metrics()["response_status"], 401)
        self.assertEqual(client.metrics()["attempts"], 1)

    def test_response_shape_failure_keeps_latency_and_attempt_metrics(self):
        client = OpenAIPlannerClient(
            api_key="sk-test", wire_api="chat_completions", max_retries=0
        )
        with patch(
            "agent.llm_planner.urllib.request.urlopen",
            return_value=_Response({"choices": []}),
        ):
            with self.assertRaises(PlanningError):
                client.complete_json([], {})

        metrics = client.metrics()
        self.assertEqual(metrics["status"], "error")
        self.assertEqual(metrics["error_type"], "response_shape_error")
        self.assertEqual(metrics["attempts"], 1)
        self.assertGreaterEqual(metrics["latency_ms"], 0)


if __name__ == "__main__":
    unittest.main()
