"""M331-B compact checks for catalog-driven general task composition."""

from __future__ import annotations

import unittest

from agent.general_runtime import GeneralAnswerComposer
from agent.models import AgentRunResult, RunStatus, StepRun
from agent.runtime_factory import build_general_runtime


class M331TaskCompositionTests(unittest.TestCase):
    def test_every_published_result_profile_has_one_general_owner(self):
        runtime = build_general_runtime("rule", "memory")
        host = runtime._domain_pack.host
        catalog = host.capability_catalog()
        result_registry = runtime._domain_pack.result_registry()

        result_types = catalog["result_types"]
        self.assertTrue(result_types)
        for item in result_types:
            result_type = item["type"]
            owner = host.result_owner_for(result_type)
            self.assertIn(owner, host.domain_ids)
            self.assertTrue(result_registry.is_registered(result_type))

    def test_catalog_and_registry_resolve_operation_specific_outputs(self):
        runtime = build_general_runtime("rule", "memory")
        registry = runtime._registry

        cases = (
            ("economic_indicator_query", {"operation": "latest"}, "economic_metrics_result"),
            ("economic_indicator_query", {"operation": "trend"}, "economic_timeseries_result"),
            ("indicator_query", {"operation": "compare"}, "indicator_comparison_result"),
        )
        for tool, arguments, expected in cases:
            with self.subTest(tool=tool, operation=arguments["operation"]):
                self.assertEqual(registry.result_type_for_tool(tool, arguments), expected)

        self.assertIsNone(registry.result_type_for_tool("indicator_query", {}))
        self.assertIsNone(
            registry.result_type_for_tool(
                "economic_indicator_query", {"operation": "not-registered"}
            )
        )

    def test_unrelated_direct_question_uses_same_general_runtime_without_tools(self):
        runtime = build_general_runtime("rule", "memory")
        result = runtime.run("请用通俗中文解释什么是反馈回路")

        self.assertEqual(result.domain_id, "general")
        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual(result.request_mode["mode"], "answer")
        self.assertEqual(result.steps, [])

    def test_partial_results_remain_readable_without_claiming_full_success(self):
        result = AgentRunResult(
            run_id="m331-partial",
            status=RunStatus.COMPLETED,
            request="查询并解释数据",
        )
        result.steps = [
            StepRun("ready", "lookup", {}, status="COMPLETED", result={"value": 1}),
            StepRun("missing", "lookup", {}, status="FAILED", error="数据源不可用"),
        ]

        answer = GeneralAnswerComposer().compose(result)

        self.assertIn("1 项可用结果", answer)
        self.assertNotIn("全部分析已完成", answer)


if __name__ == "__main__":
    unittest.main()
