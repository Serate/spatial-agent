"""Compact M302 contract for stage-aware Planner projections."""

import json
import unittest

from agent.composite_planner import LLMCompositePlanner
from agent.composite_request_context import CompositeRequestContextBuilder
from agent.composite_view import build_composite_view_projection
from result_contract import build_result_contract
from agent.runtime_core.planner_envelope import (
    PLANNER_ENVELOPE_SCHEMA_VERSION,
    PlannerEnvelopeError,
    build_execution_planner_envelope,
    build_planner_envelope,
    normalize_planner_envelope,
    project_planner_envelope_evidence,
)
from tests.test_m287_bounded_planner_repair import (
    _application as _repair_application,
    _planned_payload,
)
from tests.test_m294_execution_binding_closure import _binding
from tests.test_m299_default_agent_success_path import _context
from tests.test_m300_open_agent_success import _fixture


class _Client:
    def __init__(self):
        self.messages = []

    def complete_json(self, messages, schema):
        del schema
        self.messages.append(messages)
        return {
            "outcome": "needs_clarification",
            "goal": "",
            "message": "请补充指标。",
            "components": [],
        }


class M302StageAwarePlannerContextTests(unittest.TestCase):
    def test_stage_and_request_identity_are_stable(self):
        source = _context()
        discovery = build_planner_envelope(source, projection_stage="discovery")
        selection = build_planner_envelope(source, projection_stage="selection")
        execution_source = dict(source)
        execution_source["selected_components"] = [
            {
                "component_id": "economic-query",
                "domain_id": "economic",
                "capability_id": "trend",
                "depends_on": [],
                "required": True,
            }
        ]
        execution = build_planner_envelope(
            execution_source, projection_stage="execution"
        )

        self.assertEqual(discovery["projection_stage"], "discovery")
        self.assertEqual(selection["projection_stage"], "selection")
        self.assertEqual(execution["projection_stage"], "execution")
        self.assertEqual(
            {
                discovery["request_fingerprint"],
                selection["request_fingerprint"],
                execution["request_fingerprint"],
            },
            {"m299-request"},
        )
        self.assertNotIn("execution_contract", discovery)
        self.assertEqual(
            [item["capability_id"] for item in execution["capability_index"]],
            ["trend"],
        )
        self.assertLess(
            len(json.dumps(discovery, ensure_ascii=False)),
            len(json.dumps(selection, ensure_ascii=False)),
        )
        normalized = normalize_planner_envelope(selection)
        self.assertEqual(normalized["projection_stage"], "selection")
        self.assertEqual(normalized["request_fingerprint"], "m299-request")

    def test_selected_execution_projection_keeps_readiness_workflow_and_result_profile(self):
        source = _context()
        source["selected_components"] = [
            {
                "component_id": "economic-query",
                "domain_id": "economic",
                "capability_id": "trend",
                "depends_on": [],
                "required": True,
            }
        ]
        envelope = build_planner_envelope(source, projection_stage="execution")
        contract = envelope["execution_contract"]

        self.assertEqual(
            [item["workflow_id"] for item in contract["workflows"]],
            ["economic-trend"],
        )
        self.assertTrue(contract["capabilities"][0]["execution_ready"])
        self.assertEqual(
            contract["capabilities"][0]["output_profiles"][0]["primary"],
            "timeseries",
        )
        self.assertEqual(
            envelope["selected_components"][0]["component_id"], "economic-query"
        )
        self.assertNotIn("source_path", json.dumps(envelope, ensure_ascii=False))
        self.assertNotIn("unrelated-workflow", json.dumps(envelope, ensure_ascii=False))

    def test_context_builder_stores_discovery_and_llm_reprojects_selection(self):
        host, projector = _fixture()
        context = CompositeRequestContextBuilder(
            host=host, catalog_projector=projector
        ).build("分析武汉概况", domain_ids=["gis"])
        self.assertEqual(
            context["planner_envelope"]["projection_stage"], "discovery"
        )

        client = _Client()
        LLMCompositePlanner(client).plan("分析武汉概况", context=context)
        provider_payload = json.loads(
            client.messages[0][1]["content"].split(
                "[Trusted planner envelope]\n", 1
            )[1]
        )
        self.assertEqual(provider_payload["projection_stage"], "selection")
        self.assertEqual(provider_payload["schema_version"], PLANNER_ENVELOPE_SCHEMA_VERSION)

    def test_repair_projection_is_selected_only_and_stage_is_validated(self):
        source = _context()
        source["selected_components"] = [
            {
                "component_id": "economic-query",
                "domain_id": "economic",
                "capability_id": "trend",
                "depends_on": [],
                "required": True,
            }
        ]
        source["planner_repair"] = {
            "schema_version": "spatial-agent.planner-repair-request.v1",
            "reason_code": "plan_component_field_invalid",
            "request_fingerprint": "m299-request",
            "attempt": 1,
            "max_attempts": 1,
        }
        envelope = build_planner_envelope(source, projection_stage="repair")

        self.assertEqual(envelope["projection_stage"], "repair")
        self.assertEqual(envelope["planner_repair"]["max_attempts"], 1)
        self.assertEqual(
            envelope["execution_contract"]["capabilities"][0]["capability_id"],
            "trend",
        )
        self.assertNotIn("unrelated-workflow", json.dumps(envelope, ensure_ascii=False))
        with self.assertRaises(PlannerEnvelopeError) as raised:
            build_planner_envelope(source, projection_stage="other")
        self.assertEqual(raised.exception.code, "planner_envelope_stage_invalid")

    def test_execution_projection_is_attached_only_after_binding_gate(self):
        result = _repair_application(_planned_payload()).prepare(
            "开放式空间摘要", planner_name="replay", domain_ids=["gis"]
        )
        projection = result["planner_evidence"]["execution_projection"]

        self.assertEqual(projection["stage"], "execution")
        self.assertEqual(projection["selected_component_ids"], ["summary"])
        self.assertEqual(
            projection["execution_identity"]["component_ids"], ["summary"]
        )
        self.assertTrue(projection["execution_identity"]["binding_fingerprint"])

    def test_execution_projection_rejects_component_set_drift(self):
        context = {
            "schema_version": "spatial-agent.composite-request-context.v2",
            "request_fingerprint": "m302-context",
            "capability_index": [
                {
                    "domain_id": "gis",
                    "capability_id": "space_summary",
                    "available": True,
                    "execution_ready": True,
                    "workflow_ids": ["space_summary"],
                    "tools": ["read_summary"],
                    "result_types": ["summary_result"],
                }
            ],
            "clarification": {"state": "not_required"},
        }
        with self.assertRaises(PlannerEnvelopeError) as raised:
            build_execution_planner_envelope(
                context,
                components=[
                    {
                        "component_id": "other",
                        "domain_id": "gis",
                        "capability_id": "space_summary",
                        "depends_on": [],
                    }
                ],
                execution_binding=_binding(),
            )
        self.assertEqual(raised.exception.code, "planner_execution_binding_mismatch")

    def test_execution_projection_rejects_component_identity_drift(self):
        context = {
            "schema_version": "spatial-agent.composite-request-context.v2",
            "request_fingerprint": "m302-context",
            "capability_index": [
                {
                    "domain_id": "gis",
                    "capability_id": "space_summary",
                    "available": True,
                    "execution_ready": True,
                    "workflow_ids": ["space_summary"],
                    "tools": ["read_summary"],
                    "result_types": ["summary_result"],
                }
            ],
            "clarification": {"state": "not_required"},
        }
        with self.assertRaises(PlannerEnvelopeError) as raised:
            build_execution_planner_envelope(
                context,
                components=[
                    {
                        "component_id": "space",
                        "domain_id": "gis",
                        "capability_id": "space_summary",
                        "depends_on": ["unbound"],
                        "required": True,
                    }
                ],
                execution_binding=_binding(),
            )
        self.assertEqual(raised.exception.code, "planner_execution_binding_mismatch")

    def test_execution_evidence_is_small_and_does_not_copy_binding_plan(self):
        context = {
            "schema_version": "spatial-agent.composite-request-context.v2",
            "request_fingerprint": "m302-context",
            "capability_index": [
                {
                    "domain_id": "gis",
                    "capability_id": "space_summary",
                    "available": True,
                    "execution_ready": True,
                    "tools": ["read_summary"],
                    "result_types": ["summary_result"],
                }
            ],
            "clarification": {"state": "not_required"},
        }
        envelope = build_execution_planner_envelope(
            context,
            components=[
                {
                    "component_id": "space",
                    "domain_id": "gis",
                    "capability_id": "space_summary",
                    "depends_on": [],
                }
            ],
            execution_binding=_binding(),
        )
        evidence = project_planner_envelope_evidence(envelope)
        encoded = json.dumps(evidence, ensure_ascii=False)

        self.assertNotIn("read_summary", encoded)
        self.assertNotIn('"plan"', encoded)
        self.assertEqual(evidence["stage"], "execution")

        normalized = normalize_planner_envelope(envelope)
        self.assertEqual(
            normalized["execution_identity"]["binding_fingerprint"],
            envelope["execution_identity"]["binding_fingerprint"],
        )

    def test_composite_view_carries_safe_answer_evidence_and_tolerates_bad_counts(self):
        result = {
            "composite": {
                "schema_version": "spatial-agent.composite-result.v1",
                "request": {"fingerprint": "composite-request"},
                "state": "completed",
                "components": [
                    {
                        "component_id": "summary",
                        "domain_id": "gis",
                        "state": "completed",
                        "status": "COMPLETED",
                        "result_type": "summary_result",
                        "data_profile": {"primary": "metrics", "kinds": ["metrics"]},
                        "answer": "已形成摘要。",
                    }
                ],
                "evidence": {
                    "schema_version": "spatial-agent.composite-evidence.v1",
                    "state": "completed",
                    "component_count": "not-a-number",
                    "component_evidence": [],
                },
            },
            "planner_evidence": {
                "plan_completeness": {
                    "component_count": "invalid",
                    "materialized_count": None,
                }
            },
            "answer_generation_evidence": {
                "status": "success",
                "available": True,
                "execution_mode": "live_model",
            },
        }

        projection = build_composite_view_projection(result)

        self.assertEqual(projection["evidence"]["component_count"], 1)
        self.assertEqual(
            projection["evidence"]["answer_generation"]["status"], "success"
        )
        self.assertEqual(projection["planning"]["plan_completeness"]["component_count"], 0)

    def test_result_workspace_declares_fallback_view_specs(self):
        payload = {
            "status": "COMPLETED",
            "result_type": "admin_area_result",
            "plan": {"output": {"type": "admin_area_result"}},
            "steps": [
                {
                    "id": "admin",
                    "tool": "range_query",
                    "status": "COMPLETED",
                    "result": {"dataset": "admin_areas", "count": 1},
                }
            ],
        }

        contract = build_result_contract(payload)

        self.assertIn("map", contract["views"]["panels"])
        self.assertIn("map", contract["workspace"]["panels"])
        self.assertTrue(
            set(contract["views"]["panels"]).issubset(
                set(contract["workspace"]["panels"])
            )
        )


if __name__ == "__main__":
    unittest.main()
