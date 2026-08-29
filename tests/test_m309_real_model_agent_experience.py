"""M309-A: provider-backed plan outcomes keep one bounded status matrix."""

from __future__ import annotations

import json
import unittest

from agent.application.composite_planner import (
    CompositePlannerError,
    LLMCompositePlanner,
    ReplayCompositePlanner,
)
from agent.domain_runtime_host import DomainRuntimeHost
from agent.application.composite_planning import (
    CompositeCapabilityProjector,
    CompositePlanningApplication,
)
from agent.provider_runtime import build_planner_attempt_receipt


CONTEXT = {
    "schema_version": "spatial-agent.composite-request-context.v2",
    "request_fingerprint": "m309-context",
    "capability_index": [],
}

THREE_COMPONENT_CONTEXT = {
    "schema_version": "spatial-agent.composite-request-context.v2",
    "request_fingerprint": "m309-three-component-context",
    "capability_index": [
        {
            "domain_id": "gis",
            "capability_id": "gis.boundary",
            "available": True,
            "plan_mode": "workflow",
            "execution_ready": True,
        },
        {
            "domain_id": "economic",
            "capability_id": "economic.trend",
            "available": True,
            "plan_mode": "workflow",
            "execution_ready": True,
        },
        {
            "domain_id": "indicators",
            "capability_id": "indicators.compare",
            "available": True,
            "plan_mode": "workflow",
            "execution_ready": True,
        },
    ],
}


def _payload(outcome: str) -> dict[str, object]:
    return {
        "outcome": outcome,
        "goal": "开放式分析" if outcome == "success" else "",
        "message": "请补充信息" if outcome == "needs_clarification" else "",
        "components": [],
    }


def _three_component_payload() -> dict[str, object]:
    return {
        "outcome": "success",
        "goal": "综合分析",
        "message": "",
        "components": [
            {
                "component_id": "boundary",
                "domain_id": "gis",
                "capability_id": "gis.boundary",
                "request": "确定分析范围",
                "depends_on": [],
                "required": True,
            },
            {
                "component_id": "trend",
                "domain_id": "economic",
                "capability_id": "economic.trend",
                "request": "分析指标趋势",
                "depends_on": [],
                "required": True,
            },
            {
                "component_id": "comparison",
                "domain_id": "indicators",
                "capability_id": "indicators.compare",
                "request": "汇总并比较结果",
                "depends_on": ["boundary", "trend"],
                "required": True,
            },
        ],
    }


class _Client:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.messages = None

    def complete_json(self, messages, schema):
        self.messages = messages
        del schema
        if self.error is not None:
            raise self.error
        return self.response


class M309PlannerOutcomeMatrixTests(unittest.TestCase):
    def test_selected_raster_capability_materializes_from_dataset_fact(self):
        """A selected raster capability must cross the real preview bridge."""

        host = DomainRuntimeHost(enabled_domain_ids=["gis"])
        host.start()
        try:
            request = "查询DEM栅格元数据"
            payload = {
                "outcome": "success",
                "goal": "查询栅格元数据",
                "message": "",
                "components": [
                    {
                        "component_id": "raster",
                        "domain_id": "gis",
                        "capability_id": "raster_metadata",
                        "request": request,
                        "depends_on": [],
                        "required": True,
                    }
                ],
            }
            application = CompositePlanningApplication(
                host=host,
                projector=CompositeCapabilityProjector(host),
                planner=ReplayCompositePlanner(payload),
                composite_runs=object(),
            )

            result = application.prepare(
                request,
                planner_name="rule",
                backend="local",
                domain_ids=["gis"],
            )

            self.assertEqual(result["status"], "PLANNED")
            bridge = result["task_plan_bridge"]
            self.assertEqual(bridge["state"], "accepted")
            self.assertEqual(bridge["components"][0]["state"], "accepted")
        finally:
            host.close()

    def test_ambiguous_raster_dataset_selection_requests_clarification(self):
        host = DomainRuntimeHost(enabled_domain_ids=["gis"])
        host.start()
        try:
            request = "查询DEM和土地利用栅格元数据"
            payload = {
                "outcome": "success",
                "goal": "查询栅格元数据",
                "message": "",
                "components": [
                    {
                        "component_id": "raster",
                        "domain_id": "gis",
                        "capability_id": "raster_metadata",
                        "request": request,
                        "depends_on": [],
                        "required": True,
                    }
                ],
            }
            application = CompositePlanningApplication(
                host=host,
                projector=CompositeCapabilityProjector(host),
                planner=ReplayCompositePlanner(payload),
                composite_runs=object(),
            )

            result = application.prepare(
                request,
                planner_name="rule",
                backend="local",
                domain_ids=["gis"],
            )

            self.assertEqual(result["status"], "NEEDS_CLARIFICATION")
            self.assertNotEqual(
                result.get("error_code"), "taskplan_component_preview_failed"
            )
        finally:
            host.close()

    def test_multi_goal_model_output_becomes_three_component_canonical_plan(self):
        client = _Client(_three_component_payload())
        planner = LLMCompositePlanner(client)

        result = planner.plan(
            "确定范围、分析趋势并比较结果",
            context=THREE_COMPONENT_CONTEXT,
        )

        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(
            [item["component_id"] for item in result["components"]],
            ["boundary", "trend", "comparison"],
        )
        self.assertEqual(result["components"][2]["depends_on"], ["boundary", "trend"])
        self.assertEqual(planner.metrics()["status"], "success")

    def test_multi_goal_instruction_is_part_of_the_provider_neutral_prompt(self):
        client = _Client(_payload("needs_clarification"))
        planner = LLMCompositePlanner(client)

        planner.plan("分析多个独立目标", context=CONTEXT)

        # The prompt communicates a general decomposition policy, not a
        # domain- or region-specific recipe.
        self.assertIn("multiple independent analytical goals", client.messages[0]["content"])

    def test_minimal_client_success_is_recorded_as_completed_attempt(self):
        planner = LLMCompositePlanner(_Client(_payload("needs_clarification")))

        result = planner.plan("分析一个开放问题", context=CONTEXT)
        metrics = planner.metrics()
        receipt = build_planner_attempt_receipt(
            metrics,
            stage="selection",
            outcome="needs_clarification",
        )

        self.assertEqual(result["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(metrics["status"], "success")
        self.assertEqual(metrics["attempts"], 1)
        self.assertEqual(receipt["state"], "completed")
        self.assertEqual(receipt["outcome"], "needs_clarification")
        self.assertEqual(receipt["next_actions"], ["provide_facts"])

    def test_provider_error_is_a_retryable_provider_failure_receipt(self):
        class ProviderError(RuntimeError):
            retryable = True
            category = "network"
            code = "gateway_timeout"

        planner = LLMCompositePlanner(_Client(error=ProviderError()))
        with self.assertRaises(CompositePlannerError) as error:
            planner.plan("分析一个开放问题", context=CONTEXT)

        self.assertEqual(error.exception.code, "planner_provider_failed")
        metrics = planner.metrics()
        receipt = build_planner_attempt_receipt(
            metrics,
            stage="selection",
            outcome="provider_failure",
            reason_code="provider_timeout",
        )
        self.assertEqual(metrics["status"], "error")
        self.assertEqual(receipt["state"], "failed")
        self.assertEqual(receipt["outcome"], "provider_failure")
        self.assertTrue(receipt["retryable"])
        self.assertEqual(receipt["next_actions"], ["retry"])

    def test_semantic_rejection_stays_separate_from_provider_failure(self):
        planner = LLMCompositePlanner(_Client(_payload("rejected")))

        result = planner.plan("分析一个开放问题", context=CONTEXT)
        metrics = planner.metrics()
        receipt = build_planner_attempt_receipt(
            metrics,
            stage="selection",
            outcome="rejected",
            reason_code="planner_rejected",
        )

        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(metrics["status"], "success")
        self.assertEqual(receipt["state"], "completed")
        self.assertEqual(receipt["outcome"], "rejected")
        self.assertEqual(receipt["next_actions"], ["adjust_request"])

    def test_invalid_provider_shape_is_bounded_and_does_not_leak_content(self):
        planner = LLMCompositePlanner(
            _Client(
                {
                    "outcome": "success",
                    "goal": "开放式分析",
                    "message": "",
                    "components": [],
                    "private_response": "must-not-leak",
                }
            )
        )

        with self.assertRaises(CompositePlannerError) as error:
            planner.plan("分析一个开放问题", context=CONTEXT)

        self.assertEqual(error.exception.code, "plan_response_field_invalid")
        self.assertNotIn("must-not-leak", json.dumps(vars(error.exception), ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
