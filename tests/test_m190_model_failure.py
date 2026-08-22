"""M190-D: model provider failures remain classified and recoverable."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from agent.artifact_store import ArtifactStore
from agent.errors import PlanningError
from agent.llm_planner import OpenAIPlannerClient
from agent.models import RunStatus
from agent.runtime import AgentRuntime
from agent.service import AgentService
from agent.tools import ToolRegistry
from domains.text.domain import TEXT_DOMAIN_PACK
from domains.text.provider import TextToolProvider


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
            "usage": {"total_tokens": 12},
        }
    )


class _FailingPlanner:
    def __init__(self, *, code="provider_timeout", retryable=True):
        self.code = code
        self.retryable = retryable

    def plan(self, request, **kwargs):
        del request, kwargs
        raise PlanningError(
            "provider unavailable",
            category="provider",
            code=self.code,
            retryable=self.retryable,
        )

    def metrics(self):
        return {
            "provider": "test-provider",
            "wire_api": "chat_completions",
            "model": "test-model",
            "execution_mode": "live_model",
            "status": "error",
            "error_type": "timeout",
            "attempts": 2,
            "retries": 1,
            "latency_ms": 4.5,
        }


def _runtime_factory(planner, backend, **kwargs):
    del planner, backend
    return AgentRuntime(
        _FailingPlanner(),
        ToolRegistry.from_provider(TextToolProvider()),
        domain_pack=TEXT_DOMAIN_PACK,
        **kwargs,
    )


class M190ModelFailureTests(unittest.TestCase):
    def test_client_classifies_transient_auth_and_timeout_without_raw_provider_text(self):
        transient = urllib.error.HTTPError(
            "https://example.test",
            503,
            "temporarily unavailable",
            {},
            io.BytesIO(b"Authorization: Bearer sk-provider-secret"),
        )
        client = OpenAIPlannerClient(
            api_key="sk-test",
            wire_api="chat_completions",
            max_retries=1,
            retry_backoff_seconds=0,
        )
        with patch(
            "agent.llm_planner.urllib.request.urlopen",
            side_effect=[transient, _success_response()],
        ):
            self.assertEqual(client.complete_json([], {}), {"goal": "ok"})
        self.assertEqual(client.metrics()["retries"], 1)

        auth = OpenAIPlannerClient(
            api_key="sk-test", wire_api="chat_completions", max_retries=3
        )
        auth_error = urllib.error.HTTPError(
            "https://example.test", 401, "unauthorized", {}, io.BytesIO(b"secret")
        )
        with patch("agent.llm_planner.urllib.request.urlopen", side_effect=auth_error):
            with self.assertRaises(PlanningError) as auth_context:
                auth.complete_json([], {})
        self.assertEqual(auth_context.exception.category, "provider")
        self.assertEqual(auth_context.exception.code, "provider_authentication")
        self.assertFalse(auth_context.exception.retryable)
        self.assertNotIn("secret", str(auth_context.exception))

        timeout = OpenAIPlannerClient(
            api_key="sk-test", wire_api="chat_completions", max_retries=0
        )
        with patch("agent.llm_planner.urllib.request.urlopen", side_effect=TimeoutError()):
            with self.assertRaises(PlanningError) as timeout_context:
                timeout.complete_json([], {})
        self.assertEqual(timeout_context.exception.code, "provider_timeout")
        self.assertTrue(timeout_context.exception.retryable)

    def test_runtime_failure_contract_keeps_model_classification_and_metrics(self):
        result = AgentRuntime(
            _FailingPlanner(),
            ToolRegistry.from_provider(TextToolProvider()),
            domain_pack=TEXT_DOMAIN_PACK,
        ).run("请解释这段文本")

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertEqual(result.failure["category"], "provider")
        self.assertEqual(result.failure["code"], "provider_timeout")
        self.assertTrue(result.failure["retryable"])
        self.assertEqual(result.planner_metrics["error_type"], "timeout")
        self.assertNotIn("provider details", json.dumps(result.to_dict()))

    def test_service_async_artifact_and_restart_keep_model_failure_contract(self):
        with tempfile.TemporaryDirectory(prefix="m190-model-failure-") as directory:
            root = Path(directory)
            state_path = root / "state.db"
            artifact_root = root / "artifacts"
            service = AgentService(
                state_db_path=str(state_path),
                artifact_store=ArtifactStore(artifact_root),
                runtime_factory=_runtime_factory,
            )
            direct = service.run(
                "请解释这段文本",
                planner="openai",
                backend="memory",
                session_id="m190-model-direct",
                export_artifact=True,
            )
            artifact = json.loads(Path(direct["artifact_ref"]).read_text(encoding="utf-8"))
            submitted = service.run_async(
                request="请解释这段文本",
                planner="openai",
                backend="memory",
                session_id="m190-model-async",
                export_artifact=True,
                idempotency_key="m190-model-failure-async",
            )
            for _ in range(200):
                async_payload = service.get_run(submitted["run_id"])
                if async_payload.get("status") not in {"PLANNING", "EXECUTING"}:
                    break
            self.assertEqual(async_payload["status"], "FAILED")
            service.close()

            restarted = AgentService(
                state_db_path=str(state_path),
                artifact_store=ArtifactStore(artifact_root),
                runtime_factory=_runtime_factory,
            )
            recovered = restarted.get_run(direct["run_id"], planner="openai", backend="memory")
            restarted.close()

        expected = {
            "schema_version": "spatial-agent.failure.v1",
            "status": "FAILED",
            "category": "provider",
            "code": "provider_timeout",
            "phase": "planning",
            "retryable": True,
        }
        self.assertEqual(direct["failure"], expected)
        self.assertEqual(artifact["failure"], expected)
        self.assertEqual(async_payload["failure"], expected)
        self.assertEqual(recovered["failure"], expected)
        self.assertEqual(recovered["planner_metrics"]["error_type"], "timeout")


if __name__ == "__main__":
    unittest.main()
