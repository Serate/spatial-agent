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

    def test_llm_planner_normalizes_single_tool_success_shortcut(self):
        client = FakeLLMClient(
            {
                "outcome": "success",
                "tool": "get_raster_metadata",
                "args": {"dataset": "dem", "max_files": 3},
            }
        )

        plan = LLMPlanner(client, tool_names()).plan("query DEM metadata")

        self.assertEqual(plan.steps[0].tool, "get_raster_metadata")
        self.assertEqual(plan.steps[0].args["dataset"], "dem")
        self.assertEqual(plan.steps[0].depends_on, [])

    def test_llm_planner_still_rejects_unknown_shortcut_tool(self):
        client = FakeLLMClient(
            {"outcome": "success", "tool": "run_shell", "args": {}}
        )

        with self.assertRaises(PlanningError):
            LLMPlanner(client, tool_names()).plan("run a command")

    def test_llm_planner_normalizes_string_output_type(self):
        client = FakeLLMClient(
            {
                "goal": "inspect raster metadata",
                "steps": [
                    {"id": "raster", "tool": "get_raster_metadata", "args": {}}
                ],
                "output": "raster_metadata_result",
            }
        )

        plan = LLMPlanner(client, tool_names()).plan("query raster metadata")

        self.assertEqual(plan.output, {"type": "raster_metadata_result"})

    def test_llm_planner_accepts_direct_answer_decision(self):
        client = FakeLLMClient({
            "outcome": "direct_answer",
            "goal": "answer general question",
            "message": "这是一个通用回答。",
            "steps": [],
            "output": {"type": "direct_answer"},
        })
        plan = LLMPlanner(client, tool_names()).plan("你是谁")
        self.assertEqual(plan.steps, [])
        self.assertEqual(plan.output["message"], "这是一个通用回答。")

    def test_llm_planner_normalizes_admin_range_shortcut_arguments(self):
        client = FakeLLMClient(
            {
                "goal": "query admin boundary",
                "steps": [
                    {
                        "id": "admin-range",
                        "tool": "range_query",
                        "args": {
                            "dataset": "admin_areas",
                            "field": "name",
                            "value": "洪山区",
                        },
                        "depends_on": [],
                    }
                ],
                "output": {"type": "geojson"},
            }
        )

        plan = LLMPlanner(client, tool_names()).plan("查询洪山区行政区边界")

        self.assertEqual(
            plan.steps[0].args["conditions"],
            [{"field": "name", "operator": "eq", "value": "洪山区"}],
        )
        self.assertEqual(plan.steps[0].args["limit"], 100)
        self.assertNotIn("field", plan.steps[0].args)
        self.assertNotIn("value", plan.steps[0].args)

    def test_result_reference_requires_dependency(self):
        with self.assertRaises(PlanningError):
            parse_task_plan(
                {
                    "goal": "bind result",
                    "steps": [
                        {"id": "source", "tool": "get_dataset_schema", "args": {"dataset": "roads"}},
                        {
                            "id": "consumer",
                            "tool": "get_dataset_schema",
                            "args": {"dataset": {"$from": "source", "path": "dataset"}},
                        },
                    ],
                },
                tool_names(),
            )

    def test_result_reference_accepts_nested_path_with_dependency(self):
        plan = parse_task_plan(
            {
                "goal": "bind result",
                "steps": [
                    {"id": "source", "tool": "get_dataset_schema", "args": {"dataset": "roads"}},
                    {
                        "id": "consumer",
                        "tool": "get_dataset_schema",
                        "args": {"dataset": {"$from": "source", "path": "dataset"}},
                        "depends_on": ["source"],
                    },
                ],
            },
            tool_names(),
        )
        self.assertEqual(
            plan.steps[1].args["dataset"],
            {"$from": "source", "path": "dataset"},
        )

    def test_result_reference_rejects_malformed_object(self):
        with self.assertRaises(PlanningError):
            parse_task_plan(
                {
                    "goal": "bad reference",
                    "steps": [
                        {"id": "source", "tool": "get_dataset_schema", "args": {"dataset": "roads"}},
                        {
                            "id": "consumer",
                            "tool": "get_dataset_schema",
                            "args": {"dataset": {"$from": "source", "path": "dataset", "extra": True}},
                            "depends_on": ["source"],
                        },
                    ],
                },
                tool_names(),
            )

    def test_fake_llm_preserves_composite_result_reference_plan(self):
        client = FakeLLMClient(
            {
                "goal": "resolve area and analyze DEM",
                "steps": [
                    {"id": "schema-admin", "tool": "get_dataset_schema", "args": {"dataset": "admin_areas"}},
                    {
                        "id": "filter-admin",
                        "tool": "range_query",
                        "args": {
                            "dataset": "admin_areas",
                            "conditions": [{"field": "name", "operator": "eq", "value": "洪山区"}],
                            "limit": 100,
                        },
                        "depends_on": ["schema-admin"],
                    },
                    {
                        "id": "zonal",
                        "tool": "get_zonal_raster_statistics",
                        "args": {
                            "dataset": "dem",
                            "admin_name": {"$from": "filter-admin", "path": "first_name"},
                        },
                        "depends_on": ["filter-admin"],
                    },
                ],
                "output": {"type": "zonal_raster_statistics_result"},
            }
        )

        plan = LLMPlanner(client, tool_names()).plan("复合分析")

        self.assertEqual(plan.steps[2].args["admin_name"]["$from"], "filter-admin")


if __name__ == "__main__":
    unittest.main()
