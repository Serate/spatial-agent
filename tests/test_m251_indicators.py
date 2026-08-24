import unittest

from agent.domain_registry import domain_registry
from agent.errors import ClarificationNeeded
from agent.workflow_templates import compile_workflow_plan
from domains.indicators.planner import IndicatorsRulePlanner
from domains.indicators.workflow_templates import (
    KNOWN_RESULT_TYPES,
    KNOWN_TOOL_NAMES,
    workflow_template_catalog,
)


class M251IndicatorTests(unittest.TestCase):
    def test_array_constraint_is_compiled_through_generic_workflow_seam(self):
        compiled = compile_workflow_plan(
            "indicator_compare",
            {
                "dataset": "regional_indicators",
                "indicator": "demo_activity_index",
                "regions": ["区域甲", "区域乙"],
            },
            catalog=workflow_template_catalog(),
            known_tools=KNOWN_TOOL_NAMES,
            known_result_types=KNOWN_RESULT_TYPES,
        )
        self.assertEqual(compiled["steps"][0]["args"]["regions"], ["区域甲", "区域乙"])

    def test_indicator_domain_is_registered_and_rule_planner_requires_facts(self):
        self.assertIn("indicators", domain_registry().ids())
        with self.assertRaises(ClarificationNeeded):
            IndicatorsRulePlanner().plan("分析指标趋势")

        from agent.runtime_factory import build_runtime

        result = build_runtime("rule", "memory", domain_id="indicators").run("分析指标趋势")
        self.assertEqual(result.status.value, "NEEDS_CLARIFICATION")
        self.assertIn("indicator", result.clarification.get("missing_fields"))

    def test_indicator_trend_returns_timeseries_profile(self):
        from agent.runtime_factory import build_runtime

        result = build_runtime("rule", "memory", domain_id="indicators").run(
            "demo_activity_index 区域甲和区域乙的趋势"
        )
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "indicator_timeseries_result")
        self.assertEqual(result.steps[-1].result["data_profile"]["primary"], "timeseries")
        self.assertIn("趋势", result.answer)


if __name__ == "__main__":
    unittest.main()
