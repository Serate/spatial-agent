import unittest

from agent.errors import ToolError
from agent.models import PlanStep, TaskPlan
from agent.runtime import AgentRuntime
from agent.tools import ToolRegistry
from agent.trace_formatter import format_trace


class FailurePlanner:
    def plan(self, request):
        return TaskPlan(
            goal="exercise failure states",
            steps=[
                PlanStep("first", "make_value", {}, []),
                PlanStep("second", "fail_value", {}, ["first"]),
                PlanStep("third", "use_value", {}, ["second"]),
            ],
        )


class FailureAdapter:
    def invoke(self, name, arguments):
        if name == "make_value":
            return {"value": "retained"}
        if name == "fail_value":
            raise ToolError("simulated backend failure")
        if name == "use_value":
            return {"ok": True}
        raise AssertionError(name)


def registry():
    definitions = {
        name: {
            "name": name,
            "input_schema": {"type": "object", "additionalProperties": False},
        }
        for name in ("make_value", "fail_value", "use_value")
    }
    return ToolRegistry(definitions, FailureAdapter())


class M33FailureStateTests(unittest.TestCase):
    def test_failed_run_retains_completed_result_and_marks_remaining_blocked(self):
        result = AgentRuntime(FailurePlanner(), registry(), max_retries=0).run("fail")

        self.assertEqual(result.status.value, "FAILED")
        self.assertEqual(result.steps[0].status, "COMPLETED")
        self.assertEqual(result.steps[0].result, {"value": "retained"})
        self.assertEqual(result.steps[1].status, "FAILED")
        self.assertEqual(result.steps[2].status, "BLOCKED")
        self.assertIn("blocked by failed step second", result.steps[2].error)

        trace = format_trace(result)
        self.assertTrue(any("simulated backend failure" in line for line in trace))
        self.assertTrue(any("blocked" in line for line in trace))


if __name__ == "__main__":
    unittest.main()
