"""Compact M299 contract tests for the default Agent provider boundary."""

import json
import unittest

from agent.composite_planner import LLMCompositePlanner
from agent.runtime_core.planner_envelope import (
    PLANNER_ENVELOPE_LAYERS,
    PLANNER_ENVELOPE_SCHEMA_VERSION,
    PlannerEnvelopeError,
    build_planner_envelope,
)


def _context():
    return {
        "schema_version": "spatial-agent.composite-request-context.v2",
        "planner": "openai",
        "backend": "local",
        "request_fingerprint": "m299-request",
        "request_summary": "分析洪山区近年经济与空间变化",
        "domain_contexts": [
            {
                "domain_id": "economic",
                "facts": {
                    "schema_version": "facts.v1",
                    "admin_name": "洪山区",
                    "tasks": ["trend"],
                    "datasets": ["economic_indicators"],
                    "constraints": {"time_range": "近五年"},
                    "source_path": "D:/private/secret.csv",
                },
                "data_readiness": {"status": "ready"},
                "clarification": {"state": "not_required"},
                "discovery": {"selected_capability_id": "trend"},
            }
        ],
        "capability_index": [
            {
                "domain_id": "economic",
                "capability_id": "trend",
                "selection_key": "economic::trend",
                "label": "趋势分析",
                "description": "计算已登记指标的时间趋势",
                "available": True,
                "datasets": ["economic_indicators"],
                "result_types": ["economic_timeseries_result"],
                "output_profiles": [
                    {
                        "result_type": "economic_timeseries_result",
                        "primary": "timeseries",
                        "kinds": ["timeseries", "metrics"],
                    }
                ],
                "workflow_ids": ["economic-trend"],
                "tools": ["query_indicator", "calculate_trend"],
                "execution_ready": True,
            },
            {
                "domain_id": "gis",
                "capability_id": "boundary",
                "selection_key": "gis::boundary",
                "label": "区域边界",
                "description": "查询已登记行政区边界",
                "available": True,
                "datasets": ["admin_boundaries"],
                "result_types": ["admin_area_result"],
                "output_profiles": [
                    {
                        "result_type": "admin_area_result",
                        "primary": "vector",
                        "kinds": ["vector"],
                    }
                ],
                "workflow_ids": ["gis-boundary"],
                "tools": ["get_admin_boundary"],
                "execution_ready": True,
            },
        ],
        "workflow_index": [
            {
                "domain_id": "economic",
                "workflow_id": "economic-trend",
                "label": "指标趋势",
                "allowed_tools": ["query_indicator", "calculate_trend"],
                "result_types": ["economic_timeseries_result"],
            },
            {
                "domain_id": "economic",
                "workflow_id": "unrelated-workflow",
                "label": "不相关流程",
                "allowed_tools": ["private_tool"],
                "result_types": ["private_result"],
            },
        ],
        "discovery": {
            "state": "available",
            "reason_code": "candidates_available",
            "candidates": [{"state": "available", "domain_id": "economic", "capability_id": "trend"}],
            "next_actions": ["plan"],
        },
        "clarification": {
            "state": "not_required",
            "reason_code": "facts_and_candidates_available",
            "message": "已具备规划所需信息。",
        },
    }


class _Client:
    def __init__(self):
        self.messages = None

    def complete_json(self, messages, schema):
        self.messages = messages
        return {
            "outcome": "needs_clarification",
            "goal": "",
            "message": "请指定要比较的经济指标。",
            "components": [],
        }


class M299DefaultAgentSuccessPathTests(unittest.TestCase):
    def test_envelope_has_four_layers_and_redacts_private_context(self):
        envelope = build_planner_envelope(_context())
        encoded = json.dumps(envelope, ensure_ascii=False)

        self.assertEqual(envelope["schema_version"], PLANNER_ENVELOPE_SCHEMA_VERSION)
        self.assertEqual(envelope["layers"], list(PLANNER_ENVELOPE_LAYERS))
        self.assertTrue(envelope["redaction"]["applied"])
        self.assertNotIn("source_path", encoded)
        self.assertEqual(
            envelope["selection"]["selected_capability_keys"], ["economic::trend"]
        )

    def test_execution_layer_only_includes_candidate_workflows(self):
        envelope = build_planner_envelope(_context())
        workflows = envelope["execution_contract"]["workflows"]

        self.assertEqual([item["workflow_id"] for item in workflows], ["economic-trend"])
        self.assertEqual(
            envelope["execution_contract"]["capabilities"][0]["capability_id"],
            "trend",
        )

    def test_llm_receives_envelope_instead_of_raw_context(self):
        client = _Client()
        result = LLMCompositePlanner(client).plan("分析洪山区", context=_context())

        self.assertEqual(result["status"], "NEEDS_CLARIFICATION")
        self.assertIn("[Trusted planner envelope]", client.messages[1]["content"])
        self.assertIn(PLANNER_ENVELOPE_SCHEMA_VERSION, client.messages[1]["content"])
        self.assertNotIn("D:/private/secret.csv", client.messages[1]["content"])

    def test_envelope_budget_is_fail_closed(self):
        with self.assertRaises(PlannerEnvelopeError) as raised:
            build_planner_envelope(_context(), max_bytes=128)
        self.assertEqual(raised.exception.code, "planner_envelope_too_large")


if __name__ == "__main__":
    unittest.main()
