"""Compact M301 contract for Planner-first fact readiness."""

import unittest

from agent.composite_request_context import (
    COMPOSITE_REQUEST_CONTEXT_MAX_BYTES,
    CompositeRequestContextBuilder,
)
from agent.runtime_core.planner_envelope import PLANNER_ENVELOPE_MAX_BYTES
from agent.runtime_core.request_fact_readiness import (
    REQUEST_FACT_READINESS_SCHEMA_VERSION,
)
from tests.test_m300_open_agent_success import _fixture


class M301PlannerFirstOpenQueryTests(unittest.TestCase):
    def test_internal_context_and_provider_envelope_have_separate_budgets(self):
        self.assertGreater(COMPOSITE_REQUEST_CONTEXT_MAX_BYTES, PLANNER_ENVELOPE_MAX_BYTES)

    def test_unrelated_domain_missing_facts_are_advisory(self):
        host, projector = _fixture(domain_regions={"gis": True, "economic": False})
        context = CompositeRequestContextBuilder(
            host=host, catalog_projector=projector
        ).build("分析武汉概况", domain_ids=["gis", "economic"])

        self.assertEqual(context["clarification"]["state"], "advisory")
        self.assertEqual(
            context["clarification"]["reason_code"], "domain_facts_pending"
        )
        readiness = {
            item["domain_id"]: item["fact_readiness"]
            for item in context["domain_contexts"]
        }
        self.assertEqual(
            readiness["gis"]["schema_version"],
            REQUEST_FACT_READINESS_SCHEMA_VERSION,
        )
        self.assertEqual(readiness["gis"]["state"], "complete")
        self.assertEqual(readiness["economic"]["state"], "missing")
        self.assertEqual(
            context["planner_envelope"]["request_facts"]["domains"][1][
                "fact_readiness"
            ]["state"],
            "missing",
        )


if __name__ == "__main__":
    unittest.main()
