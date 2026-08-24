import json
import unittest

from agent.llm_planner import LLMPlanner
from agent.domain_contract import planner_guidance
from agent.runtime_factory import build_runtime
from domains.gis.domain import GIS_DOMAIN_PACK


class _OpenSpatialPlanClient:
    def __init__(self):
        self.messages = []

    def complete_json(self, messages, schema):
        self.messages.append(messages)
        return {
            "goal": "clip roads to the selected administrative region",
            "steps": [
                {
                    "id": "spatial-operation",
                    "tool": "spatial_operation",
                    "args": {
                        "operation": "clip",
                        "input_ref": "roads",
                        "mask_ref": "admin_areas",
                    },
                    "depends_on": [],
                }
            ],
            "output": {"type": "spatial_operation_result", "summary": True},
        }


class M249OpenPlannerTests(unittest.TestCase):
    def test_selected_open_capability_reaches_llm_planner_context(self):
        request = "裁剪洪山区道路"
        runtime = build_runtime("rule", "memory")
        packet = runtime._build_context_packet(request, request, "m249-open", None)
        sections = packet.payload["sections"]

        self.assertEqual(
            sections["workflow_selection"]["selected_capability_id"],
            "vector_operation",
        )
        self.assertIn(
            "vector_operation",
            [item["id"] for item in sections["capability_catalog"]["capabilities"]],
        )
        self.assertIn(
            "vector_operation",
            [item["id"] for item in sections["workflow_templates"]["templates"]],
        )

        client = _OpenSpatialPlanClient()
        planner = LLMPlanner(
            client,
            runtime._registry.names,
            planner_guidance=planner_guidance(GIS_DOMAIN_PACK),
        )
        plan = planner.plan(request, context=packet.payload)

        self.assertEqual(plan.steps[0].tool, "spatial_operation")
        self.assertEqual(plan.output["type"], "spatial_operation_result")
        prompt = json.dumps(client.messages, ensure_ascii=False)
        self.assertIn("spatial_operation", prompt)
        self.assertIn("spatial_operation_result", prompt)


if __name__ == "__main__":
    unittest.main()
