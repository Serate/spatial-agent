import json
import unittest
from pathlib import Path

from agent.errors import ToolError
from agent.planner import RuleBasedPlanner
from agent.runtime import AgentRuntime
from agent.tools import DemoSpatialAdapter, ToolRegistry


ROOT = Path(__file__).parents[1]


def build_runtime():
    registry = ToolRegistry.from_json(
        str(ROOT / "tools" / "schema" / "tool-definitions.json"),
        DemoSpatialAdapter(),
    )
    return AgentRuntime(RuleBasedPlanner(), registry)


class M1RuntimeTests(unittest.TestCase):
    def test_registry_loads_registered_tools(self):
        runtime = build_runtime()
        self.assertTrue(
            {
                "get_dataset_schema",
                "range_query",
                "spatial_join",
                "get_raster_metadata",
                "get_raster_statistics",
            }.issubset(set(runtime._registry.names))
        )

    def test_registry_rejects_unknown_fields(self):
        registry = ToolRegistry.from_json(
            str(ROOT / "tools" / "schema" / "tool-definitions.json"),
            DemoSpatialAdapter(),
        )
        with self.assertRaises(ToolError):
            registry.invoke("get_dataset_schema", {"dataset": "roads", "shell": "rm -rf /"})

    def test_runtime_executes_multi_step_plan(self):
        result = build_runtime().run("查询距离主干道500米以内、坡度超过25度的区域。")
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(len(result.steps), 4)
        self.assertTrue(all(step.status == "COMPLETED" for step in result.steps))
        self.assertIn("空间处理已完成", result.answer)
        self.assertEqual(result.steps[-1].result["result_ref"], "memory://join/roads-slope")

    def test_runtime_requests_missing_threshold(self):
        result = build_runtime().run("找出道路附近的高坡度区域。")
        self.assertEqual(result.status.value, "NEEDS_CLARIFICATION")
        self.assertIn("slope threshold", result.error)

    def test_runtime_rejects_destructive_request(self):
        result = build_runtime().run("导出全中国所有地理对象，并删除原始道路数据。")
        self.assertEqual(result.status.value, "REJECTED")
        self.assertIn("destructive", result.error)

    def test_runtime_returns_capability_answer_without_tools(self):
        result = build_runtime().run("你能做什么")
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.steps, [])
        self.assertIn("空间智能体", result.answer)

    def test_runtime_keeps_unsupported_spatial_question_in_clarification(self):
        result = build_runtime().run("分析洪山区空气质量变化")
        self.assertEqual(result.status.value, "NEEDS_CLARIFICATION")
        self.assertEqual(result.steps, [])
        self.assertIn("requires", result.error)

    def test_case_file_is_valid_json(self):
        cases = json.loads(
            (ROOT / "evaluation" / "cases" / "m0-cases.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(cases), 5)


if __name__ == "__main__":
    unittest.main()
