import unittest

from agent.composite_planner import (
    CompositePlannerError,
    LLMCompositePlanner,
    normalize_provider_response,
    normalize_composite_plan,
)
from agent.composite_request_context import _candidate_projection


class _Client:
    def __init__(self):
        self.messages = None

    def complete_json(self, messages, schema):
        self.messages = messages
        return {
            "outcome": "success",
            "goal": "组合查询",
            "message": "",
            "components": [
                {
                    "component_id": "gis-step",
                    "domain_id": "gis",
                    "capability_id": "spatial_overview",
                    "request": "查询空间总览",
                    "depends_on": [],
                    "required": True,
                }
            ],
        }


class M286ProviderPlannerAdaptationTests(unittest.TestCase):
    def test_candidate_projection_exposes_copyable_identity_and_tools(self):
        projected = _candidate_projection(
            [
                {
                    "id": "spatial_overview",
                    "label": "空间总览",
                    "description": "bounded",
                    "datasets": ["dem"],
                    "tools": ["get_raster_metadata"],
                    "result_types": ["raster_metadata_result"],
                    "available": True,
                    "availability_reason": "ready",
                }
            ],
            ["spatial_overview"],
            domain_id="gis",
        )
        self.assertEqual(projected[0]["domain_id"], "gis")
        self.assertEqual(projected[0]["capability_id"], "spatial_overview")
        self.assertEqual(projected[0]["selection_key"], "gis::spatial_overview")
        self.assertEqual(projected[0]["tools"], ["get_raster_metadata"])

    def test_llm_prompt_requires_exact_registered_identity(self):
        client = _Client()
        planner = LLMCompositePlanner(client)
        planner.plan(
            "查询空间总览",
            context={
                "schema_version": "spatial-agent.composite-request-context.v2",
                "capability_index": [
                    {
                        "domain_id": "gis",
                        "capability_id": "spatial_overview",
                        "selection_key": "gis::spatial_overview",
                        "tools": ["get_raster_metadata"],
                        "available": True,
                    }
                ],
            },
        )
        system = client.messages[0]["content"]
        user = client.messages[1]["content"]
        self.assertIn("Copy each domain_id and capability_id exactly", system)
        self.assertIn("gis::spatial_overview", user)

    def test_non_success_components_are_rejected_before_execution(self):
        with self.assertRaises(CompositePlannerError) as raised:
            normalize_composite_plan(
                {
                    "outcome": "needs_clarification",
                    "goal": "",
                    "message": "缺少区域",
                    "components": [{"domain_id": "gis"}],
                },
                request="查询空间总览",
                context=None,
                planner_source="replay",
            )
        self.assertEqual(raised.exception.code, "plan_components_unexpected")

    def test_provider_plan_over_budget_is_rejected_instead_of_truncated(self):
        with self.assertRaises(CompositePlannerError) as raised:
            normalize_provider_response(
                {
                    "outcome": "success",
                    "goal": "组合查询",
                    "message": "",
                    "components": [{} for _ in range(9)],
                }
            )
        self.assertEqual(raised.exception.code, "plan_components_limit")


if __name__ == "__main__":
    unittest.main()
