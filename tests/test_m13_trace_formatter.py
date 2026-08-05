import unittest

from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from agent.planner import RuleBasedPlanner
from agent.runtime import AgentRuntime
from agent.service import AgentService
from agent.tools import DemoSpatialAdapter, ToolRegistry
from agent.trace_formatter import format_trace
from pathlib import Path


ROOT = Path(__file__).parents[1]
ADMIN_QUERY = "\u67e5\u8be2\u6d2a\u5c71\u533a\u884c\u653f\u533a\u8fb9\u754c"
GENERIC_ADMIN_QUERY = "\u67e5\u8be2\u884c\u653f\u533a\u8fb9\u754c"
ADMIN_NAME = "\u6d2a\u5c71\u533a"
DESTRUCTIVE_QUERY = "\u5bfc\u51fa\u5168\u4e2d\u56fd\u6240\u6709\u5730\u7406\u5bf9\u8c61\uff0c\u5e76\u5220\u9664\u539f\u59cb\u9053\u8def\u6570\u636e\u3002"


def build_runtime():
    registry = ToolRegistry.from_json(
        str(ROOT / "tools" / "schema" / "tool-definitions.json"),
        DemoSpatialAdapter(),
    )
    return AgentRuntime(RuleBasedPlanner(), registry)


class M13TraceFormatterTests(unittest.TestCase):
    def test_completed_run_trace_includes_goal_tools_and_answer(self):
        result = build_runtime().run(ADMIN_QUERY)
        trace = format_trace(result)
        self.assertIn("Received request: " + ADMIN_QUERY, trace[0])
        self.assertTrue(any("Planned goal: query admin area boundary by name" in line for line in trace))
        self.assertTrue(any("Tool get_dataset_schema(admin_areas) completed" in line for line in trace))
        self.assertTrue(any("Tool range_query(admin_areas) completed" in line for line in trace))
        self.assertTrue(any("Final answer:" in line for line in trace))

    def test_clarification_trace_explains_waiting_state(self):
        result = build_runtime().run(GENERIC_ADMIN_QUERY)
        trace = format_trace(result)
        self.assertTrue(any("Planning stopped:" in line for line in trace))
        self.assertTrue(any("Waiting for user clarification." in line for line in trace))

    def test_rejected_trace_explains_rejection(self):
        result = build_runtime().run(DESTRUCTIVE_QUERY)
        trace = format_trace(result)
        self.assertTrue(any("Request rejected:" in line for line in trace))

    def test_service_response_includes_trace_summary(self):
        service = AgentService()
        first = service.run(GENERIC_ADMIN_QUERY, session_id="m13")
        second = service.run(ADMIN_NAME, session_id="m13")
        self.assertIn("trace_summary", first)
        self.assertIn("trace_summary", second)
        self.assertTrue(any("Waiting for user clarification." in line for line in first["trace_summary"]))
        self.assertTrue(any("Resolved request:" in line for line in second["trace_summary"]))

    def test_raster_trace_includes_metadata_summary(self):
        result = AgentRunResult(
            run_id="run-1",
            status=RunStatus.COMPLETED,
            request="query raster metadata",
            plan=TaskPlan(
                goal="Query DEM raster metadata",
                steps=[PlanStep("raster", "get_raster_metadata", {"dataset": "dem"})],
            ),
            steps=[
                StepRun(
                    id="raster",
                    tool="get_raster_metadata",
                    args={"dataset": "dem"},
                    status="COMPLETED",
                    result={
                        "dataset": "dem",
                        "file_count": 9,
                        "metadata": {"width": 100, "height": 80},
                        "metrics": {"probed_files": 2},
                    },
                )
            ],
            answer="dem raster metadata: file_count=9",
        )

        trace = "\n".join(format_trace(result))

        self.assertIn("file_count=9", trace)
        self.assertIn("probed_files=2", trace)
        self.assertIn("size=100x80", trace)


if __name__ == "__main__":
    unittest.main()
