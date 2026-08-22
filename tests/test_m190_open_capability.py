"""M190: open-request discovery exposes one bounded next-step contract."""

from __future__ import annotations

import unittest

from agent.capability_discovery import (
    DISCOVERY_GUIDANCE_SCHEMA_VERSION,
    discover_from_catalog,
    enrich_discovery_context,
)
from agent.errors import ClarificationNeeded
from agent.request_model import RequestFacts
from agent.selection_interaction import build_selection_interaction
from run_demo import build_runtime


def _facts(**values):
    return RequestFacts(
        text="",
        admin_name=values.get("admin_name"),
        tasks=tuple(values.get("tasks", ())),
        datasets=tuple(values.get("datasets", ())),
        constraints=dict(values.get("constraints", {})),
        evidence=(),
    )


class _ClarifyingPlanner:
    def plan(self, request, **kwargs):
        del request, kwargs
        raise ClarificationNeeded("需要补充能力和输入事实")


class M190OpenCapabilityTests(unittest.TestCase):
    def test_matched_capability_projects_missing_facts_without_domain_branch(self):
        definitions = [
            {
                "id": "custom_analysis",
                "label": "自定义分析",
                "request_hints": {"phrases": ["custom analysis"]},
                "request_requirements": {
                    "clarification_fields": [
                        {"id": "region", "label": "分析区域", "kind": "entity", "key": "region"},
                        {"id": "limit", "label": "分析阈值", "kind": "constraint", "keys": ["limit"]},
                    ]
                },
                "result_types": ["custom_result"],
            }
        ]
        discovery = discover_from_catalog("run custom analysis", _facts(), definitions)
        projection = enrich_discovery_context(
            discovery,
            _facts(),
            {"capabilities": definitions},
        )

        self.assertEqual(projection["guidance"]["schema_version"], DISCOVERY_GUIDANCE_SCHEMA_VERSION)
        self.assertEqual(projection["guidance"]["state"], "clarification")
        self.assertEqual(
            [item["label"] for item in projection["missing_fields"]],
            ["分析区域", "分析阈值"],
        )
        self.assertEqual(projection["suggested_capability_details"], [])

    def test_unmatched_discovery_exposes_bounded_catalog_choices(self):
        definitions = [
            {"id": "alpha", "label": "甲能力", "result_types": ["alpha_result"]},
            {"id": "beta", "label": "乙能力", "result_types": ["beta_result"]},
        ]
        projection = enrich_discovery_context(
            {
                "schema_version": "spatial-agent.capability-discovery.v1",
                "selection_state": "unavailable",
                "candidate_ids": [],
            },
            _facts(),
            {"capabilities": definitions},
            max_suggestions=1,
        )

        guidance = projection["guidance"]
        self.assertEqual(guidance["state"], "unavailable")
        self.assertEqual(guidance["suggested_capability_ids"], ["alpha"])
        self.assertEqual(projection["suggested_capability_details"][0]["label"], "甲能力")

    def test_runtime_plan_evidence_carries_open_request_choices(self):
        runtime = build_runtime("rule", "memory")
        runtime._planner = _ClarifyingPlanner()
        payload = runtime.preview("查询一个尚未注册的空间对象")

        self.assertEqual(payload["status"], "NEEDS_CLARIFICATION")
        selection = payload["plan_evidence"]["workflow_selection"]
        self.assertEqual(selection["state"], "unavailable")
        self.assertTrue(selection["suggested_capability_details"])
        self.assertEqual(
            selection["suggested_capability_details"][0]["actions"],
            ["select_capability", "preview"],
        )
        interaction = build_selection_interaction(
            selection=selection,
            clarification={"missing_fields": [{"id": "object", "label": "空间对象"}]},
            status="NEEDS_CLARIFICATION",
        )
        self.assertIn("select_capability", interaction["allowed_actions"])


if __name__ == "__main__":
    unittest.main()
