"""Compact M304 provider health/deadline and user projection contract."""

from __future__ import annotations

import json
import unittest

from agent.environment_status import environment_status
from agent.application.composite_planner import CompositePlannerError, LLMCompositePlanner
from agent.application.composite_planning import CompositePlanningApplication
from agent.application.composite_view import build_composite_view_projection
from agent.errors import PlanningError
from agent.provider_runtime import (
    PROVIDER_HEALTH_SCHEMA_VERSION,
    PROVIDER_RUNTIME_SCHEMA_VERSION,
    build_provider_deadline_receipt,
    build_provider_health,
    project_provider_runtime_evidence,
)


class M304ProviderRuntimeTests(unittest.TestCase):
    def test_planning_failure_maps_provider_code_and_retry_action(self):
        class _Planner:
            def plan(self, request, *, context=None):
                del request, context
                raise CompositePlannerError(
                    "provider failed",
                    code="planner_provider_failed",
                    details={
                        "provider_failure": {
                            "code": "provider_timeout",
                            "retryable": True,
                        }
                    },
                )

        class _Context:
            def build(self, request, **kwargs):
                del request, kwargs
                return {
                    "schema_version": "spatial-agent.composite-request-context.v2",
                    "request_fingerprint": "m304-provider-failure",
                    "clarification": {"state": "not_required"},
                    "capability_index": [],
                }

        result = CompositePlanningApplication(
            host=object(),
            projector=object(),
            planner=_Planner(),
            composite_runs=object(),
            context_builder=_Context(),
        ).prepare("规划组合分析", planner_name="openai", backend="local")

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure"]["code"], "provider_timeout")
        self.assertTrue(result["failure"]["retryable"])
        self.assertEqual(result["next_actions"], ["稍后重试"])

    def test_llm_planner_preserves_bounded_provider_failure_metadata(self):
        class _Client:
            def complete_json(self, messages, schema):
                del messages, schema
                raise PlanningError(
                    "provider timeout",
                    category="provider",
                    code="provider_timeout",
                    retryable=True,
                )

        planner = LLMCompositePlanner(_Client())
        with self.assertRaises(CompositePlannerError) as error:
            planner.plan("规划组合分析", context={})

        details = getattr(error.exception, "details", {})
        self.assertEqual(details["provider_failure"]["code"], "provider_timeout")
        self.assertTrue(details["provider_failure"]["retryable"])

    def test_llm_composite_planner_uses_one_compact_recovery_for_invalid_json(self):
        calls = []

        class _Client:
            def complete_json(self, messages, schema):
                calls.append("normal")
                raise PlanningError(
                    "invalid model response",
                    category="planning",
                    code="invalid_model_response",
                    retryable=False,
                )

            def complete_compact_json(self, messages, schema, *, schema_name=None):
                calls.append("compact")
                return {
                    "outcome": "needs_clarification",
                    "goal": "",
                    "message": "需要补充信息",
                    "components": [],
                }

        planner = LLMCompositePlanner(_Client())
        result = planner.plan("规划组合分析", context={})

        self.assertEqual(result["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(calls, ["normal", "compact"])
        self.assertEqual(planner.metrics()["compact_recovery_attempts"], 1)

    def test_llm_composite_prompt_excludes_unready_capabilities(self):
        captured = []

        class _Client:
            def complete_json(self, messages, schema, **kwargs):
                del schema, kwargs
                captured.extend(messages)
                return {
                    "outcome": "needs_clarification",
                    "goal": "",
                    "message": "没有可执行能力",
                    "components": [],
                }

        LLMCompositePlanner(_Client()).plan(
            "组合分析",
            context={
                "capability_index": [
                    {
                        "domain_id": "gis",
                        "capability_id": "unbound",
                        "available": True,
                        "execution_ready": False,
                        "plan_mode": "unbound",
                    },
                    {
                        "domain_id": "gis",
                        "capability_id": "ready",
                        "available": True,
                        "execution_ready": True,
                    },
                ]
            },
        )
        system = next(item["content"] for item in captured if item["role"] == "system")
        self.assertIn("execution_ready", system)
        self.assertIn("workflow_not_registered", system)

    def test_provider_runtime_survives_composite_view_projection(self):
        runtime = project_provider_runtime_evidence(
            {
                "status": "error",
                "error_type": "timeout",
                "attempts": 1,
                "retries": 0,
            },
            provider_health=build_provider_health(
                {
                    "api_key": "secret",
                    "model": "safe-model",
                    "base_url": "https://gateway.example/v1",
                },
                network_checked=False,
            ),
        )
        view = build_composite_view_projection(
            {
                "status": "FAILED",
                "planner_evidence": {"provider_runtime": runtime},
                "composite": {"state": "failed", "components": [], "evidence": {}},
            }
        )

        self.assertEqual(
            view["planning"]["provider_runtime"],
            runtime,
        )
        self.assertNotIn("secret", json.dumps(view))

    def test_health_is_safe_and_reports_structured_capability(self):
        health = build_provider_health(
            {
                "api_key": "sk-never-render-this",
                "model": "deepseek-v4-flash",
                "base_url": "https://gateway.example/v1",
                "wire_api": "chat_completions",
                "structured_output_mode": "json_schema",
            },
            network_available=True,
            network_checked=True,
        )

        self.assertEqual(health["schema_version"], PROVIDER_HEALTH_SCHEMA_VERSION)
        self.assertEqual(health["status"], "ready")
        self.assertEqual(health["network"], "reachable")
        self.assertEqual(health["structured_output"]["structured_mode"], "json_schema")
        self.assertNotIn("sk-never-render-this", json.dumps(health))

    def test_health_distinguishes_missing_key_and_unreachable_network(self):
        missing = build_provider_health(
            {"base_url": "https://gateway.example/v1"},
            network_available=True,
            network_checked=True,
        )
        unreachable = build_provider_health(
            {"api_key": "configured", "base_url": "https://gateway.example/v1"},
            network_available=False,
            network_checked=True,
        )

        self.assertEqual(missing["status"], "unavailable")
        self.assertEqual(missing["reason_code"], "api_key_missing")
        self.assertEqual(unreachable["reason_code"], "network_unavailable")

    def test_deadline_receipt_normalizes_timeout_and_bad_metrics(self):
        receipt = build_provider_deadline_receipt(
            {
                "status": "error",
                "error_type": "timeout",
                "attempts": "bad",
                "retries": 3,
                "timeout_seconds": 60,
                "latency_ms": float("inf"),
            },
            harness_timeout_seconds=90,
        )

        self.assertEqual(receipt["state"], "timed_out")
        self.assertTrue(receipt["deadline_exceeded"])
        self.assertTrue(receipt["retryable"])
        self.assertNotIn("attempts", receipt)
        self.assertEqual(receipt["retries"], 3)
        self.assertEqual(receipt["reason_code"], "provider_timeout")

    def test_runtime_evidence_is_idempotently_projected(self):
        source = {
            "status": "error",
            "error_type": "url_error",
            "attempts": 2,
            "retries": 1,
            "provider_health": build_provider_health(
                {
                    "api_key": "secret",
                    "model": "safe-model",
                    "base_url": "https://gateway.example/v1",
                },
                network_checked=False,
            ),
        }
        first = project_provider_runtime_evidence(source)
        second = project_provider_runtime_evidence(first)

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], PROVIDER_RUNTIME_SCHEMA_VERSION)
        self.assertEqual(first["deadline"]["reason_code"], "provider_network")
        self.assertNotIn("secret", json.dumps(first))

    def test_environment_status_keeps_legacy_flags_and_adds_health(self):
        status = environment_status()
        self.assertIn("live_llm", status["capabilities"])
        self.assertIn("live_llm_network", status["capabilities"])
        self.assertEqual(
            status["provider_health"]["schema_version"], PROVIDER_HEALTH_SCHEMA_VERSION
        )


if __name__ == "__main__":
    unittest.main()
