import unittest

from agent.errors import ClarificationNeeded, PlanningError, RequestRejected
from agent.llm_planner import LLMPlanner
from agent.plan_schema import parse_task_plan, task_plan_schema
from agent.tools import DemoSpatialAdapter, ToolRegistry
from pathlib import Path


ROOT = Path(__file__).parents[1]


class FakeLLMClient:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None
        self.schema = None

    def complete_json(self, messages, schema):
        self.messages = messages
        self.schema = schema
        return self.payload


def tool_names():
    registry = ToolRegistry.from_json(
        str(ROOT / "tools" / "schema" / "tool-definitions.json"),
        DemoSpatialAdapter(),
    )
    return registry.names


class M2LLMPlannerTests(unittest.TestCase):
    def test_task_plan_schema_is_strict_object(self):
        schema = task_plan_schema()
        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("steps", schema["required"])

    def test_parse_task_plan_rejects_unknown_tool(self):
        with self.assertRaises(PlanningError):
            parse_task_plan(
                {
                    "goal": "bad",
                    "steps": [{"id": "x", "tool": "run_shell", "args": {}}],
                },
                tool_names(),
            )

    def test_llm_planner_returns_task_plan_from_json_payload(self):
        client = FakeLLMClient(
            {
                "goal": "identify high-slope areas near roads",
                "steps": [
                    {
                        "id": "schema-roads",
                        "tool": "get_dataset_schema",
                        "args": {"dataset": "roads"},
                    },
                    {
                        "id": "near-roads",
                        "tool": "spatial_join",
                        "args": {
                            "left_dataset": "roads",
                            "right_dataset": "slope",
                            "relation": "near",
                            "distance_m": 500,
                        },
                        "depends_on": ["schema-roads"],
                    },
                ],
                "output": {"type": "spatial_result"},
            }
        )
        plan = LLMPlanner(client, tool_names()).plan("query")
        self.assertEqual(plan.goal, "identify high-slope areas near roads")
        self.assertEqual(len(plan.steps), 2)
        self.assertIn("get_dataset_schema", client.messages[0]["content"])

    def test_llm_planner_surfaces_clarification(self):
        client = FakeLLMClient(
            {"outcome": "needs_clarification", "message": "missing distance"}
        )
        with self.assertRaises(ClarificationNeeded):
            LLMPlanner(client, tool_names()).plan("near roads")

    def test_llm_planner_surfaces_rejection(self):
        client = FakeLLMClient({"outcome": "rejected", "message": "destructive"})
        with self.assertRaises(RequestRejected):
            LLMPlanner(client, tool_names()).plan("delete roads")


if __name__ == "__main__":
    unittest.main()
