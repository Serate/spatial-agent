import unittest
from unittest.mock import patch

from agent.domain_contract import rule_planner
from agent.models import TaskPlan
from agent.planner import RuleBasedPlanner as LegacyRuleBasedPlanner
from agent.rule_planning import RuleBasedPlanComposer as LegacyPlanComposer
from agent.runtime_factory import build_runtime
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.gis.planner import RuleBasedPlanner as GisRuleBasedPlanner
from domains.gis.rule_planning import RuleBasedPlanComposer as GisPlanComposer
from domains.text.domain import TEXT_DOMAIN_PACK
from domains.text.runtime import build_text_runtime


class M131DomainPlannerTests(unittest.TestCase):
    def test_each_domain_declares_a_deterministic_planner_adapter(self):
        gis_planner = rule_planner(GIS_DOMAIN_PACK)
        text_planner = rule_planner(TEXT_DOMAIN_PACK)

        self.assertEqual(type(gis_planner).__name__, "RuleBasedPlanner")
        self.assertEqual(type(text_planner).__name__, "TextSummaryPlanner")
        self.assertTrue(callable(gis_planner.plan))
        self.assertTrue(callable(text_planner.plan))

    def test_runtime_factory_uses_selected_domain_planner(self):
        class SentinelPlanner:
            def plan(self, request, workflow=None, context=None):
                return TaskPlan(
                    goal="sentinel",
                    steps=[],
                    output={"type": "direct_answer", "message": "sentinel"},
                )

        sentinel = SentinelPlanner()
        with patch.object(GIS_DOMAIN_PACK, "rule_planner", return_value=sentinel):
            runtime = build_runtime("rule", "memory")

        self.assertIs(runtime._planner, sentinel)

    def test_gis_planner_implementation_is_domain_owned(self):
        planner = rule_planner(GIS_DOMAIN_PACK)

        self.assertIsInstance(planner, GisRuleBasedPlanner)
        self.assertEqual(type(planner).__module__, "domains.gis.planner")
        self.assertEqual(type(planner._composer).__module__, "domains.gis.rule_planning")
        self.assertIsInstance(planner._composer, GisPlanComposer)

    def test_legacy_planner_and_composer_remain_bounded_adapters(self):
        legacy_planner = LegacyRuleBasedPlanner()
        legacy_composer = LegacyPlanComposer()

        self.assertEqual(type(legacy_planner).__module__, "agent.planner")
        self.assertEqual(type(legacy_planner._delegate).__module__, "domains.gis.planner")
        self.assertEqual(type(legacy_composer).__module__, "agent.rule_planning")
        self.assertEqual(type(legacy_composer._delegate).__module__, "domains.gis.rule_planning")

    def test_text_runtime_still_completes_through_domain_planner(self):
        result = build_text_runtime().run("请摘要这段文本")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "text_summary_result")
        self.assertEqual(result.plan_evidence["domain_id"], "text")


if __name__ == "__main__":
    unittest.main()
