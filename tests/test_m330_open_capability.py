"""Compact M330-B contracts for catalog-driven open actions."""

from __future__ import annotations

import unittest

from agent.models import PlanStep, TaskPlan
from agent.runtime_factory import build_general_runtime
from agent.runtime_core.execution_policy import ExecutionPolicyError


class M330OpenCapabilityTests(unittest.TestCase):
    def test_general_catalog_keeps_multiple_domain_owners(self):
        runtime = build_general_runtime("rule", "memory")
        catalog = runtime._domain_pack.capability_catalog()

        self.assertEqual(catalog["domain_id"], "general")
        self.assertGreaterEqual(len(catalog["domain_ids"]), 4)
        self.assertIn("economic_indicator_query", catalog["tool_owners"])
        self.assertIn("indicator_query", catalog["tool_owners"])
        self.assertGreaterEqual(catalog["capability_descriptor_count"], 4)

    def test_operation_specific_result_type_comes_from_workflow_contract(self):
        runtime = build_general_runtime("rule", "memory")
        registry = runtime._registry

        self.assertEqual(
            registry.result_type_for_tool("economic_list_indicators", {}),
            "economic_catalog_result",
        )
        self.assertEqual(
            registry.result_type_for_tool(
                "economic_indicator_query", {"operation": "latest"}
            ),
            "economic_metrics_result",
        )
        self.assertEqual(
            registry.result_type_for_tool(
                "indicator_query", {"operation": "compare"}
            ),
            "indicator_comparison_result",
        )

    def test_ambiguous_or_undeclared_result_type_fails_closed(self):
        runtime = build_general_runtime("rule", "memory")
        registry = runtime._registry

        self.assertIsNone(registry.result_type_for_tool("indicator_query", {}))
        self.assertIsNone(
            registry.result_type_for_tool(
                "economic_indicator_query", {"operation": "invented"}
            )
        )

    def test_model_invented_result_label_is_rejected_before_execution(self):
        runtime = build_general_runtime("rule", "memory")
        plan = TaskPlan(
            goal="查询指标",
            steps=[PlanStep("step", "economic_list_indicators", {})],
            output={"type": "model_invented_result"},
        )

        with self.assertRaises(ExecutionPolicyError):
            runtime._planning_surface.validate_plan_for_execution(
                plan,
                None,
                policy_mode="open_react",
            )


if __name__ == "__main__":
    unittest.main()
