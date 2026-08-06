import unittest

from agent.models import PlanStep, TaskPlan
from agent.plan_schema import parse_task_plan
from agent.planner import Planner
from agent.runtime import AgentRuntime, _resolve_result_references
from agent.tools import ToolRegistry
from agent.errors import ToolError


class BindingPlanner(Planner):
    def plan(self, request):
        return TaskPlan(
            goal="bind a previous result",
            steps=[
                PlanStep("source", "make_value", {}, []),
                PlanStep(
                    "consumer",
                    "use_value",
                    {"value": {"$from": "source", "path": "value"}},
                    ["source"],
                ),
            ],
        )


class BindingAdapter:
    def invoke(self, name, arguments):
        if name == "make_value":
            return {"value": "洪山区", "nested": {"ok": True}}
        if name == "use_value":
            return {"received": arguments["value"]}
        raise AssertionError(name)


class M32ResultReferenceTests(unittest.TestCase):
    def test_runtime_resolves_previous_result_before_dispatch(self):
        registry = ToolRegistry(
            {
                "make_value": {
                    "name": "make_value",
                    "input_schema": {"type": "object", "additionalProperties": False},
                },
                "use_value": {
                    "name": "use_value",
                    "input_schema": {
                        "type": "object",
                        "required": ["value"],
                        "properties": {"value": {"type": "string"}},
                        "additionalProperties": False,
                    },
                },
            },
            BindingAdapter(),
        )
        result = AgentRuntime(BindingPlanner(), registry).run("bind")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.steps[1].args, {"value": "洪山区"})
        self.assertEqual(result.steps[1].result["received"], "洪山区")

    def test_runtime_rejects_unknown_result_reference_path(self):
        with self.assertRaises(ToolError):
            _resolve_result_references(
                {"value": {"$from": "source", "path": "missing"}},
                {"source": {"value": "洪山区"}},
            )

    def test_runtime_rejects_dependency_on_later_step(self):
        class OutOfOrderPlanner(Planner):
            def plan(self, request):
                return TaskPlan(
                    goal="out of order",
                    steps=[
                        PlanStep("consumer", "use_value", {}, ["source"]),
                        PlanStep("source", "make_value", {}, []),
                    ],
                )

        registry = ToolRegistry(
            {
                "make_value": {"name": "make_value", "input_schema": {"type": "object"}},
                "use_value": {"name": "use_value", "input_schema": {"type": "object"}},
            },
            BindingAdapter(),
        )
        result = AgentRuntime(OutOfOrderPlanner(), registry).run("order")

        self.assertEqual(result.status.value, "FAILED")
        self.assertIn("earlier step", result.error)


if __name__ == "__main__":
    unittest.main()
