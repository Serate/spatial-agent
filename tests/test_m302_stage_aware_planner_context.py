"""Compact M302 contract for stage-aware Planner projections."""

import json
import unittest

from agent.composite_planner import LLMCompositePlanner
from agent.composite_request_context import CompositeRequestContextBuilder
from agent.runtime_core.planner_envelope import (
    PLANNER_ENVELOPE_SCHEMA_VERSION,
    PlannerEnvelopeError,
    build_planner_envelope,
    normalize_planner_envelope,
)
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


if __name__ == "__main__":
    unittest.main()
