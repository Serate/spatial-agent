"""M141 covers bounded repair of valid-shaped but invalid TaskPlans."""

import unittest

from agent.llm_planner import LLMPlanner
from agent.replanning import ReplanningPolicy
from agent.runtime import AgentRuntime
from agent.trace_formatter import format_trace
from agent.tools import ToolRegistry
from result_contract import build_result_contract


class _ValueAdapter:
    def invoke(self, name, arguments):
        if name == "make_value":
            return {"value": "ready"}
        if name == "use_value":
            return {"ok": True}
        if name == "range_query":
            return {"count": 1, "features": []}
        raise AssertionError("unexpected tool: " + name)


class _RecordedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete_json(self, messages, schema):
        del messages, schema
        self.calls += 1
        return self.responses.pop(0)

    def metrics(self):
        return {
            "provider": "offline-replay",
            "status": "success",
            "usage": {"total_tokens": 12},
            "latency_ms": 2,
            "attempts": 1,
            "retries": 0,
        }


def _registry():
    definitions = {
        name: {
            "name": name,
            "input_schema": {"type": "object", "additionalProperties": True},
        }
        for name in ("make_value", "use_value")
    }
    return ToolRegistry(definitions, _ValueAdapter())


def _range_registry():
    definitions = {
        "range_query": {
            "name": "range_query",
            "input_schema": {
                "type": "object",
                "required": ["conditions", "limit"],
                "properties": {
                    "conditions": {"type": "array"},
                    "limit": {"type": "integer"},
                },
                "additionalProperties": True,
            },
        }
    }
    return ToolRegistry(definitions, _ValueAdapter())


class M141PlanRepairTests(unittest.TestCase):
    def test_llm_plan_validation_failure_is_repaired_before_execution(self):
        client = _RecordedClient(
            [
                {
                    "goal": "invalid dependency plan",
                    "steps": [
                        {"id": "first", "tool": "make_value", "args": {}},
                        {
                            "id": "final",
                            "tool": "use_value",
                            "args": {},
                            "depends_on": ["missing-step"],
                        },
                    ],
                    "output": {"type": "value_result"},
                },
                {
                    "goal": "repaired plan",
                    "steps": [
                        {"id": "first", "tool": "make_value", "args": {}},
                        {
                            "id": "final",
                            "tool": "use_value",
                            "args": {},
                            "depends_on": ["first"],
                        },
                    ],
                    "output": {"type": "value_result"},
                },
            ]
        )
        runtime = AgentRuntime(
            LLMPlanner(client, ("make_value", "use_value")),
            _registry(),
            max_retries=0,
            replan_policy=ReplanningPolicy(limit=1),
        )

        result = runtime.run("repair the value plan")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(client.calls, 2)
        self.assertEqual([step.status for step in result.steps], ["COMPLETED", "COMPLETED"])
        self.assertEqual(len(result.replan_events), 1)
        event = result.replan_events[0]
        self.assertEqual(event["phase"], "planning")
        self.assertEqual(event["failed_step_id"], "plan-validation")
        self.assertEqual(event["failed_tool"], "planner")
        self.assertEqual(event["replanned_step_ids"], ["first", "final"])
        contract = build_result_contract(result.to_dict())
        self.assertEqual(contract["replanning"]["events"][0]["phase"], "planning")
        self.assertTrue(any("Adaptive replan (planning)" in line for line in format_trace(result)))

    def test_plan_repair_is_bounded_when_the_repaired_plan_is_invalid(self):
        client = _RecordedClient(
            [
                {
                    "goal": "invalid dependency plan",
                    "steps": [
                        {"id": "first", "tool": "make_value", "args": {}, "depends_on": ["missing"]}
                    ],
                    "output": {"type": "value_result"},
                },
                {
                    "goal": "still invalid",
                    "steps": [
                        {"id": "first", "tool": "make_value", "args": {}, "depends_on": ["missing"]}
                    ],
                    "output": {"type": "value_result"},
                },
            ]
        )
        runtime = AgentRuntime(
            LLMPlanner(client, ("make_value", "use_value")),
            _registry(),
            max_retries=0,
            replan_policy=ReplanningPolicy(limit=1),
        )

        result = runtime.run("do not loop repair")

        self.assertEqual(result.status.value, "FAILED")
        self.assertEqual(client.calls, 2)
        self.assertEqual(len(result.replan_events), 0)

    def test_preview_uses_the_repaired_plan_and_exposes_bounded_evidence(self):
        client = _RecordedClient(
            [
                {
                    "goal": "invalid preview plan",
                    "steps": [
                        {
                            "id": "final",
                            "tool": "use_value",
                            "args": {},
                            "depends_on": ["missing-step"],
                        }
                    ],
                    "output": {"type": "value_result"},
                },
                {
                    "goal": "repaired preview plan",
                    "steps": [{"id": "final", "tool": "use_value", "args": {}}],
                    "output": {"type": "value_result"},
                },
            ]
        )
        runtime = AgentRuntime(
            LLMPlanner(client, ("make_value", "use_value")),
            _registry(),
            replan_policy=ReplanningPolicy(limit=1),
        )

        preview = runtime.preview("preview the value plan")

        self.assertEqual(preview["status"], "PLANNED")
        self.assertEqual(client.calls, 2)
        self.assertEqual(preview["plan"]["steps"][0]["id"], "final")
        self.assertEqual(preview["replan_events"][0]["phase"], "planning")

    def test_tool_validation_failure_uses_execution_replan_phase(self):
        client = _RecordedClient(
            [
                {
                    "goal": "invalid range query",
                    "steps": [{"id": "query", "tool": "range_query", "args": {}}],
                    "output": {"type": "value_result"},
                },
                {
                    "goal": "repaired range query",
                    "steps": [
                        {
                            "id": "query",
                            "tool": "range_query",
                            "args": {"conditions": [], "limit": 100},
                        }
                    ],
                    "output": {"type": "value_result"},
                },
            ]
        )
        runtime = AgentRuntime(
            LLMPlanner(client, ("range_query",)),
            _range_registry(),
            max_retries=0,
            replan_policy=ReplanningPolicy(limit=1),
        )

        result = runtime.run("repair the range query")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(client.calls, 2)
        self.assertEqual(result.replan_events[0]["phase"], "execution")
        self.assertEqual(result.replan_events[0]["failure_category"], "tool_validation")


if __name__ == "__main__":
    unittest.main()
