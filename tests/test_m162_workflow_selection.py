"""M162: capability-to-workflow selection is a public, domain-neutral contract."""

import unittest
from pathlib import Path

from tests.console_source import read_console_source

from agent.runtime_factory import build_runtime
from agent.workflow_selection import (
    WORKFLOW_SELECTION_SCHEMA_VERSION,
    build_workflow_selection_evidence,
    normalize_workflow_selection_evidence,
)
from evaluation.contract_harness import normalize_result
from result_contract import build_result_contract
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.text.domain import TEXT_DOMAIN_PACK


class M162WorkflowSelectionTests(unittest.TestCase):
    def test_ambiguous_discovery_is_structured_without_domain_terms(self):
        evidence = build_workflow_selection_evidence(
            discovery={
                "schema_version": "spatial-agent.capability-discovery.v1",
                "candidate_ids": ["capability_a", "capability_b"],
                "candidate_count": 2,
            },
            domain_id="example",
            request_facts={"tasks": ["inspect"], "datasets": ["records"]},
        )
        self.assertEqual(evidence["schema_version"], WORKFLOW_SELECTION_SCHEMA_VERSION)
        self.assertEqual(evidence["state"], "ambiguous")
        self.assertEqual(evidence["reason_code"], "multiple_capabilities")
        self.assertEqual(evidence["candidate_ids"], ["capability_a", "capability_b"])
        self.assertEqual(evidence["fact_keys"], ["tasks", "datasets"])
        self.assertNotIn("admin_name", str(evidence))

    def test_explicit_workflow_overrides_discovery_source(self):
        evidence = build_workflow_selection_evidence(
            discovery={"selected_capability_id": "summary", "candidate_ids": ["summary"]},
            workflow={"template_id": "summary_v2", "template_version": "2.0.0"},
            domain_id="text",
        )
        self.assertEqual(evidence["state"], "selected")
        self.assertEqual(evidence["source"], "explicit_workflow")
        self.assertEqual(evidence["selected_by"], "user")
        self.assertEqual(evidence["workflow_template_id"], "summary_v2")

    def test_unknown_schema_degrades_safely(self):
        normalized = normalize_workflow_selection_evidence(
            {"schema_version": "future.v9", "domain_id": "example", "candidate_ids": ["x"]}
        )
        self.assertEqual(normalized["schema_version"], WORKFLOW_SELECTION_SCHEMA_VERSION)
        self.assertEqual(normalized["state"], "unavailable")
        self.assertEqual(normalized["reason_code"], "selection_unknown_schema")
        self.assertEqual(normalized["candidate_ids"], [])

    def test_text_runtime_and_harness_share_selection_evidence(self):
        runtime = build_runtime("rule", "memory", domain_pack=TEXT_DOMAIN_PACK)
        result = runtime.run("概括这段文本")
        payload = result.to_dict()
        payload["answer"] = result.answer
        payload["result_type"] = "text_summary_result"
        payload["result"] = build_result_contract(payload, registry=runtime.result_registry())
        planning = payload["result"]["planning"]
        self.assertEqual(
            planning["workflow_selection"]["schema_version"],
            WORKFLOW_SELECTION_SCHEMA_VERSION,
        )
        self.assertEqual(planning["workflow_selection"]["selected_capability_id"], "text_summary")
        contract = normalize_result(payload).as_dict()
        self.assertEqual(contract["workflow_selection"], planning["workflow_selection"])

    def test_gis_clarification_keeps_selection_projection(self):
        runtime = build_runtime("rule", "memory", domain_pack=GIS_DOMAIN_PACK)
        result = runtime.run("进行空间分析")
        self.assertEqual(result.status.value, "NEEDS_CLARIFICATION")
        selection = result.plan_evidence["workflow_selection"]
        self.assertEqual(selection["schema_version"], WORKFLOW_SELECTION_SCHEMA_VERSION)
        self.assertIn(selection["state"], {"ambiguous", "unavailable", "clarification"})
        self.assertEqual(selection["domain_id"], "gis")

    def test_console_renders_selection_from_structured_planning_evidence(self):
        source = read_console_source(Path(__file__).parents[1])
        self.assertIn("workflowSelection", source)
        self.assertIn("工作流选择：", source)


if __name__ == "__main__":
    unittest.main()
