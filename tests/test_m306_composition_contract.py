"""Compact M306-A contract checks for open component composition."""

import unittest

from agent.application.composite_contract import CompositeContractError, normalize_composite_request
from agent.runtime_core.analysis_discovery import AnalysisDiscoveryGateway
from agent.runtime_core.composition import CompositionError, normalize_component_inputs
from agent.runtime_core.composite_taskplan import (
    CompositeTaskPlanBridge,
    CompositeTaskPlanBridgeError,
)
from agent.runtime_core.planner_envelope import build_planner_envelope


def _component(component_id, *, depends_on=None, required=True, inputs=None):
    value = {
        "component_id": component_id,
        "domain_id": "gis",
        "request": "执行组件分析",
        "depends_on": list(depends_on or []),
        "required": required,
    }
    if inputs is not None:
        value["inputs"] = inputs
    return value


class M306CompositionContractTests(unittest.TestCase):
    def test_typed_input_canonicalizes_source_identity_and_keeps_boolean(self):
        value = normalize_component_inputs(
            [
                {
                    "name": "上游结果",
                    "source": {"component_id": "Source", "path": "result.items"},
                    "accepted_kinds": ["vector"],
                    "required": False,
                }
            ]
        )

        self.assertEqual(value[0]["source"]["component_id"], "source")
        self.assertFalse(value[0]["required"])

    def test_typed_input_rejects_internal_path_and_non_boolean_required(self):
        with self.assertRaises(CompositionError) as path_error:
            normalize_component_inputs(
                [
                    {
                        "name": "结果",
                        "source": {"component_id": "source", "path": "result.__private"},
                        "accepted_kinds": ["vector"],
                        "required": True,
                    }
                ]
            )
        self.assertEqual(path_error.exception.code, "composition_input_source_invalid")

        with self.assertRaises(CompositionError) as flag_error:
            normalize_component_inputs(
                [
                    {
                        "name": "结果",
                        "source": {"component_id": "source", "path": "result"},
                        "accepted_kinds": ["vector"],
                        "required": "false",
                    }
                ]
            )
        self.assertEqual(flag_error.exception.code, "composition_input_required_invalid")

    def test_request_rejects_non_boolean_component_required(self):
        with self.assertRaises(CompositeContractError) as error:
            normalize_composite_request(
                {
                    "schema_version": "spatial-agent.composite-request.v1",
                    "request": "组合分析",
                    "components": [_component("source", required="false")],
                }
            )
        self.assertEqual(error.exception.code, "composite_boolean_invalid")

    def test_request_requires_dependency_to_precede_consumer(self):
        with self.assertRaises(CompositeContractError) as error:
            normalize_composite_request(
                {
                    "schema_version": "spatial-agent.composite-request.v1",
                    "request": "组合分析",
                    "components": [
                        _component("consumer", depends_on=["source"]),
                        _component("source"),
                    ],
                }
            )
        self.assertEqual(error.exception.code, "composition_dependency_order_invalid")

    def test_candidate_fact_gap_is_scoped_and_survives_planner_projection(self):
        candidate = {
            "domain_id": "gis",
            "capability_id": "summary",
            "available": True,
            "plan_mode": "workflow",
            "missing_fact_ids": ["region"],
            "missing_facts": [{"id": "region", "label": "分析范围", "kind": "entity"}],
        }
        receipt = AnalysisDiscoveryGateway().discover(
            "分析空间摘要",
            planner="openai",
            backend="local",
            domain_ids=["gis"],
            domain_contexts=[
                {
                    "domain_id": "gis",
                    "discovery": {"state": "not_declared"},
                    "data_readiness": {"status": "ready"},
                    "fact_readiness": {"state": "complete"},
                }
            ],
            candidate_index=[candidate],
        )

        self.assertEqual(receipt["state"], "needs_facts")
        self.assertEqual(receipt["candidates"][0]["state"], "facts_missing")
        self.assertEqual(
            receipt["clarification"]["missing_by_candidate"][0]["capability_id"],
            "summary",
        )
        envelope = build_planner_envelope(
            {
                "schema_version": "spatial-agent.composite-request-context.v2",
                "request_fingerprint": "m306",
                "domain_contexts": [],
                "capability_index": [candidate],
                "workflow_index": [],
                "data_readiness": {"status": "ready"},
            },
            projection_stage="selection",
        )
        self.assertEqual(envelope["capability_index"][0]["missing_fact_ids"], ["region"])

    def test_taskplan_bridge_rechecks_graph_before_materialization(self):
        with self.assertRaises(CompositeTaskPlanBridgeError) as error:
            CompositeTaskPlanBridge(host=object()).bridge(
                [
                    _component("consumer", depends_on=["source"]),
                    _component("source"),
                ],
                context={},
                planner="replay",
                backend="memory",
            )
        self.assertEqual(error.exception.code, "composition_dependency_order_invalid")


if __name__ == "__main__":
    unittest.main()
