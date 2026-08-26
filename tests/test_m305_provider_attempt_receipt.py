from __future__ import annotations

import json
import unittest

from tests.test_m303_open_composite_execution import (
    _ExecutionContext,
    _ExecutionHost,
    _two_component_payload,
)

from agent.composite_planner import LLMCompositePlanner
from agent.application.composite_planning import CompositePlanningApplication
from agent.application.composite_runs import _safe_planning_evidence
from agent.composite_planner import ReplayCompositePlanner
from agent.provider_runtime import (
    PLANNER_ATTEMPT_RECEIPT_SCHEMA_VERSION,
    build_planner_attempt_receipt,
    project_planner_attempt_receipt,
)
from agent.runtime_core.plan_receipt import (
    build_canonical_plan_receipt,
    project_canonical_plan_receipt,
)


class M305PlannerAttemptReceiptTests(unittest.TestCase):
    def test_canonical_receipt_requires_accepted_bridge_and_validated_binding(self):
        result = CompositePlanningApplication(
            host=_ExecutionHost(),
            projector=object(),
            planner=ReplayCompositePlanner(_two_component_payload()),
            composite_runs=object(),
            context_builder=_ExecutionContext(),
        ).prepare(
            "分析空间与指标",
            planner_name="replay",
            domain_ids=["gis", "economic"],
        )
        receipt = result["canonical_plan"]
        self.assertEqual(receipt["state"], "executable")
        self.assertTrue(receipt["executable"])
        self.assertEqual(receipt["component_ids"], ["source", "target"])
        self.assertEqual(
            project_canonical_plan_receipt(receipt),
            receipt,
        )
        self.assertEqual(
            build_canonical_plan_receipt({}, result["execution_binding"])["executable"],
            False,
        )

    def test_llm_planner_metrics_include_actual_selection_envelope_size(self):
        class _Client:
            def complete_json(self, messages, schema):
                del messages, schema
                return {
                    "outcome": "needs_clarification",
                    "message": "需要补充信息",
                    "components": [],
                }

        planner = LLMCompositePlanner(_Client())
        result = planner.plan("请分析这个问题", context={})

        self.assertEqual(result["status"], "NEEDS_CLARIFICATION")
        metrics = planner.metrics()
        self.assertEqual(metrics["projection_stage"], "selection")
        self.assertGreater(metrics["envelope_bytes"], 0)
        self.assertEqual(metrics["envelope_max_bytes"], 96000)

    def test_timeout_receipt_keeps_budget_and_safe_failure_state(self):
        receipt = build_planner_attempt_receipt(
            {
                "status": "error",
                "error_type": "timeout",
                "attempts": 1,
                "retries": 0,
                "timeout_seconds": 60,
                "latency_ms": 60001,
            },
            stage="selection",
            request_budget={
                "envelope_max_bytes": 96000,
                "envelope_bytes": 18240,
                "output_max_tokens": 4096,
                "harness_timeout_seconds": 90,
            },
        )

        self.assertEqual(receipt["schema_version"], PLANNER_ATTEMPT_RECEIPT_SCHEMA_VERSION)
        self.assertEqual(receipt["outcome"], "provider_failure")
        self.assertEqual(receipt["state"], "timed_out")
        self.assertEqual(receipt["reason_code"], "provider_timeout")
        self.assertEqual(receipt["budget"]["envelope_bytes"], 18240)
        self.assertTrue(receipt["retryable"])
        self.assertEqual(receipt["next_actions"], ["retry"])

    def test_success_receipt_does_not_accept_unknown_stage_or_outcome(self):
        receipt = build_planner_attempt_receipt(
            {"status": "success", "attempts": 1, "retries": 0},
            stage="not-a-stage",
            outcome="not-an-outcome",
        )

        self.assertEqual(receipt["stage"], "selection")
        self.assertEqual(receipt["outcome"], "success")
        self.assertEqual(receipt["state"], "completed")
        self.assertEqual(receipt["next_actions"], ["submit"])

    def test_projection_is_idempotent_and_drops_untrusted_fields(self):
        source = {
            "schema_version": PLANNER_ATTEMPT_RECEIPT_SCHEMA_VERSION,
            "stage": "repair",
            "state": "completed",
            "outcome": "success",
            "attempts": 1,
            "retries": 0,
            "retryable": False,
            "reason_code": "plan_repaired",
            "budget": {"envelope_bytes": 12, "prompt": "private"},
            "prompt": "private",
        }

        first = project_planner_attempt_receipt(source)
        second = project_planner_attempt_receipt(first)

        self.assertEqual(first, second)
        self.assertNotIn("prompt", json.dumps(first))
        self.assertNotIn("private", json.dumps(first))

    def test_planning_receipts_survive_async_safe_evidence_projection(self):
        safe = _safe_planning_evidence(
            {
                "schema_version": "spatial-agent.composite-planner-evidence.v1",
                "planner_source": "replay",
                "planner_attempt": {
                    "schema_version": PLANNER_ATTEMPT_RECEIPT_SCHEMA_VERSION,
                    "stage": "selection",
                    "state": "completed",
                    "outcome": "success",
                    "attempts": 1,
                    "retries": 0,
                },
                "canonical_plan": {
                    "schema_version": "spatial-agent.canonical-plan-receipt.v1",
                    "state": "executable",
                    "executable": True,
                    "component_ids": ["space"],
                },
            }
        )

        self.assertEqual(safe["planner_attempt"]["outcome"], "success")
        self.assertTrue(safe["canonical_plan"]["executable"])


if __name__ == "__main__":
    unittest.main()
