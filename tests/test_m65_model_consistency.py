import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.llm_planner import LLMPlanner
from agent.runtime import AgentRuntime
from agent.tools import DemoSpatialAdapter, ToolRegistry


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "m67_spatial_overview_model.json"
EXPECTED_TOOLS = [
    "get_dataset_health_report",
    "get_dataset_schema",
    "range_query",
    "get_zonal_raster_statistics",
    "get_zonal_slope_statistics",
    "get_zonal_land_use_distribution",
    "get_zonal_vector_summary",
    "get_zonal_vector_summary",
]
EXPECTED_IDS = [
    "dataset-health",
    "schema-admin",
    "filter-admin",
    "overview-elevation",
    "overview-slope",
    "overview-land-use",
    "overview-roads",
    "overview-water",
]


class RecordedSpatialOverviewLLM:
    """Offline stand-in for a recorded structured model response."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete_json(self, messages, schema):
        self.calls.append({"messages": messages, "schema": schema})
        return copy.deepcopy(self.response)


class RecordingSpatialAdapter(DemoSpatialAdapter):
    def __init__(self):
        super().__init__()
        self.calls = []

    def invoke(self, name, arguments):
        self.calls.append((name, copy.deepcopy(arguments)))
        return super().invoke(name, arguments)


def load_recorded_response():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["response"]


def build_recorded_runtime():
    adapter = RecordingSpatialAdapter()
    registry = ToolRegistry.from_json(
        str(ROOT / "tools" / "schema" / "tool-definitions.json"), adapter
    )
    client = RecordedSpatialOverviewLLM(load_recorded_response())
    planner = LLMPlanner(client, registry.names)
    runtime = AgentRuntime(planner, registry)
    return runtime, client, adapter


class M65ModelConsistencyTests(unittest.TestCase):
    def test_recorded_response_is_parsed_as_the_eight_step_contract(self):
        runtime, client, _ = build_recorded_runtime()

        with patch("urllib.request.urlopen", side_effect=AssertionError("network access")):
            result = runtime.run("分析洪山区空间概况")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(client.calls[0]["schema"]["type"], "object")
        self.assertEqual([step.id for step in result.steps], EXPECTED_IDS)
        self.assertEqual([step.tool for step in result.steps], EXPECTED_TOOLS)
        self.assertEqual(result.plan.output["type"], "spatial_overview_result")
        self.assertEqual(result.plan.output["summary"], True)

    def test_recorded_plan_dependencies_form_the_required_dag(self):
        response = load_recorded_response()
        runtime, _, _ = build_recorded_runtime()
        plan = runtime._planner.plan("分析洪山区空间概况")

        self.assertEqual([step.id for step in plan.steps], EXPECTED_IDS)
        self.assertEqual(plan.steps[0].depends_on, [])
        self.assertEqual(plan.steps[1].depends_on, ["dataset-health"])
        self.assertEqual(plan.steps[2].depends_on, ["schema-admin"])
        for step in plan.steps[3:]:
            self.assertEqual(step.depends_on, ["filter-admin"])
        self.assertEqual(
            response["steps"][3]["args"]["admin_name"],
            {"$from": "filter-admin", "path": "first_name"},
        )

    def test_runtime_executes_each_recorded_step_through_tool_registry(self):
        runtime, _, adapter = build_recorded_runtime()

        result = runtime.run("分析洪山区空间概况")

        self.assertEqual([name for name, _ in adapter.calls], EXPECTED_TOOLS)
        self.assertEqual(len(adapter.calls), 8)
        self.assertTrue(all(step.status == "COMPLETED" for step in result.steps))
        self.assertTrue(all(isinstance(step.result, dict) for step in result.steps))
        self.assertEqual(adapter.calls[2][1]["conditions"][0]["value"], "洪山区")
        self.assertEqual(adapter.calls[3][1]["admin_name"], "洪山区")
        self.assertEqual(adapter.calls[6][1]["dataset"], "roads")
        self.assertEqual(adapter.calls[7][1]["dataset"], "water")


if __name__ == "__main__":
    unittest.main()
