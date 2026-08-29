"""M327-B compact tests for descriptor context and selection evidence."""

import unittest

from agent.capability_catalog import capability_context_summary
from agent.capability_descriptor import build_capability_descriptor
from agent.capability_selection import (
    CAPABILITY_SELECTION_EVIDENCE_SCHEMA_VERSION,
    build_capability_selection_evidence,
    normalize_capability_selection_evidence,
)
from agent.planner_context import project_planner_sections
from agent.evidence.projection import project_evidence_projection
from result_contract import build_result_contract


def _descriptor(capability_id="regional_analysis"):
    return build_capability_descriptor(
        {
            "id": capability_id,
            "label": "区域分析",
            "description": "根据可用数据完成区域指标分析。",
            "datasets": ["regional_data"],
            "tools": ["regional_query"],
            "result_types": ["regional_metrics_result"],
            "analysis_operations": ["query", "aggregate"],
            "environments": ["memory", "local"],
            "request_requirements": {
                "entities": ["region"],
                "constraints": ["period"],
            },
            "available": True,
            "availability_mode": "native",
            "capability_status": "ready",
            "internal_prompt": "must not cross the descriptor boundary",
        },
        domain_id="regional",
        catalog_version="1.0",
    )


class M327CapabilitySelectionTests(unittest.TestCase):
    def test_planner_receives_bounded_descriptors(self):
        descriptor = _descriptor()
        catalog = {
            "schema_version": "spatial-agent.capability-catalog-context.v1",
            "domain_id": "regional",
            "version": "1.0",
            "capabilities": [],
            "capability_descriptor_schema_version": descriptor["schema_version"],
            "capability_descriptor_count": 1,
            "capability_descriptors": [descriptor],
            "tool_schemas": {},
        }
        context = capability_context_summary(
            catalog=catalog,
            selected_capability_ids=["regional_analysis"],
            max_capabilities=1,
        )
        sections = project_planner_sections(
            capability_discovery={"schema_version": "discovery"},
            capability_catalog=context,
            workflow_selection={},
            workflow_templates={},
        )
        projected = sections["capability_catalog"]["capability_descriptors"]
        self.assertEqual(projected[0]["capability_id"], "regional_analysis")
        self.assertEqual(projected[0]["outputs"]["result_types"], ["regional_metrics_result"])
        self.assertNotIn("internal_prompt", str(projected))
        self.assertNotIn("arguments", str(projected))

    def test_selection_receipt_contains_choice_reason_and_safe_candidate_cards(self):
        evidence = build_capability_selection_evidence(
            discovery={
                "domain_id": "regional",
                "candidate_ids": ["regional_analysis"],
                "selected_capability_id": "regional_analysis",
                "selection_state": "selected",
                "signals": ["经济指标"],
            },
            selection={
                "state": "selected",
                "source": "domain_discovery",
                "reason_code": "capability_selected",
                "selected_capability_id": "regional_analysis",
                "candidate_ids": ["regional_analysis"],
                "missing_fields": [],
                "fact_keys": ["entities", "constraints"],
            },
            capability_catalog={"capability_descriptors": [_descriptor()]},
        )
        self.assertEqual(
            evidence["schema_version"], CAPABILITY_SELECTION_EVIDENCE_SCHEMA_VERSION
        )
        self.assertEqual(evidence["chosen_capability_id"], "regional_analysis")
        self.assertEqual(evidence["reason_code"], "capability_selected")
        self.assertEqual(evidence["candidate_summaries"][0]["capability_id"], "regional_analysis")
        self.assertNotIn("regional_query", str(evidence["candidate_summaries"]))
        self.assertNotIn("经济指标", str(evidence["candidate_summaries"]))

    def test_missing_facts_and_unknown_schema_fail_closed(self):
        evidence = build_capability_selection_evidence(
            discovery={"candidate_ids": ["regional_analysis"]},
            selection={
                "state": "clarification",
                "reason_code": "selection_requires_facts",
                "candidate_ids": ["regional_analysis"],
                "missing_fields": [{"id": "period", "label": "分析期间", "kind": "constraint"}],
            },
        )
        self.assertEqual(evidence["state"], "clarification")
        self.assertEqual(evidence["missing_fact_ids"], ["period"])
        self.assertEqual(evidence["candidate_ids"], ["regional_analysis"])

        unavailable = build_capability_selection_evidence(
            discovery={
                "domain_id": "regional",
                "selection_state": "unavailable",
                "discovery_reason_code": "no_matching_capability",
            },
            selection={"state": "unavailable", "candidate_ids": []},
        )
        self.assertFalse(unavailable["available"])
        self.assertEqual(unavailable["reason_code"], "no_matching_capability")

        unknown = normalize_capability_selection_evidence(
            {"schema_version": "spatial-agent.capability-selection.v99"}
        )
        self.assertFalse(unknown["available"])
        self.assertEqual(unknown["reason_code"], "capability_selection_unknown_schema")

    def test_result_and_shared_evidence_projection_keep_the_same_receipt(self):
        selection = build_capability_selection_evidence(
            discovery={
                "domain_id": "regional",
                "candidate_ids": ["regional_analysis"],
                "selected_capability_id": "regional_analysis",
                "selection_state": "selected",
                "discovery_reason_code": "capability_selected",
            },
            capability_catalog={"capability_descriptors": [_descriptor()]},
        )
        payload = {
            "run_id": "m327-selection",
            "domain_id": "regional",
            "status": "COMPLETED",
            "request": "查询区域指标",
            "answer": "已完成。",
            "plan": {
                "goal": "查询区域指标",
                "steps": [],
                "output": {"type": "regional_metrics_result"},
            },
            "steps": [],
            "plan_evidence": {"capability_selection": selection},
            "result_type": "regional_metrics_result",
        }
        contract = build_result_contract(payload)
        self.assertEqual(
            contract["planning"]["capability_selection"]["chosen_capability_id"],
            "regional_analysis",
        )
        projection = project_evidence_projection({"result": contract})
        self.assertEqual(
            projection["selection"]["capability_selection"],
            contract["planning"]["capability_selection"],
        )


if __name__ == "__main__":
    unittest.main()
