import unittest

from agent.request_understanding import (
    REQUEST_UNDERSTANDING_GUIDANCE_SCHEMA_VERSION,
    normalize_request_understanding_guidance,
)
from agent.planner import RuleBasedPlanner
from domains.text.domain import TEXT_DOMAIN_PACK
from domains.text.runtime import build_text_runtime
from run_demo import build_runtime


class M130RequestUnderstandingTests(unittest.TestCase):
    def test_guidance_projection_is_bounded_and_versioned(self):
        guidance = normalize_request_understanding_guidance(
            {
                "domain_id": "demo",
                "fact_fields": ["text"] * 100,
                "task_hints": [{"id": "summarize", "phrases": ["摘要"]}],
                "unexpected": "must not be copied",
            }
        )

        self.assertEqual(
            guidance["schema_version"],
            REQUEST_UNDERSTANDING_GUIDANCE_SCHEMA_VERSION,
        )
        self.assertEqual(len(guidance["fact_fields"]), 16)
        self.assertNotIn("unexpected", guidance)

    def test_gis_guidance_enters_context_and_plan_evidence(self):
        result = build_runtime("rule", "memory").run("查询洪山区行政区边界")

        section = result.context_evidence["section_names"]
        self.assertIn("request_understanding", section)
        self.assertTrue(result.plan_evidence["request_understanding_available"])
        self.assertEqual(
            result.plan_evidence["request_understanding_domain_id"],
            "gis",
        )
        self.assertEqual(result.plan_evidence["domain_id"], "gis")

    def test_text_guidance_does_not_inherit_gis_vocabulary(self):
        runtime = build_text_runtime()
        result = runtime.run("请摘要这段文本")
        guidance = normalize_request_understanding_guidance(
            TEXT_DOMAIN_PACK.request_understanding_guidance()
        )

        rendered = str(guidance)
        self.assertEqual(guidance["domain_id"], "text")
        self.assertEqual(result.plan_evidence["request_understanding_domain_id"], "text")
        self.assertNotIn("洪山区", rendered)
        self.assertNotIn("DEM", rendered)
        self.assertNotIn("道路", rendered)

    def test_rule_planner_consumes_runtime_facts_instead_of_reextracting(self):
        plan = RuleBasedPlanner().plan(
            "查询洪山区行政区边界",
            context={
                "sections": {
                    "spatial_request": {
                        "schema_version": "spatial-agent.request-facts.v1",
                        "admin_name": "江夏区",
                        "tasks": ["admin_boundary"],
                        "datasets": ["admin_areas"],
                        "constraints": {},
                        "evidence": ["geometry"],
                    }
                }
            },
        )

        self.assertEqual(
            plan.steps[1].args["conditions"][0]["value"],
            "江夏区",
        )


if __name__ == "__main__":
    unittest.main()
