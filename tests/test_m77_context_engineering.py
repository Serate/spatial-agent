import json
import tempfile
import unittest
from pathlib import Path

from agent.context_engineering import CONTEXT_SCHEMA_VERSION, ContextBuilder
from agent.llm_planner import LLMPlanner
from agent.models import PlanStep, TaskPlan
from agent.runtime import AgentRuntime
from agent.sqlite_store import SQLiteStateStore
from agent.tools import DemoSpatialAdapter, ToolRegistry


ROOT = Path(__file__).parents[1]


class ContextAwarePlanner:
    def __init__(self):
        self.context = None

    def plan(self, request, context=None):
        self.context = context
        return TaskPlan(
            goal="answer with controlled context",
            steps=[PlanStep("schema", "get_dataset_schema", {"dataset": "roads"})],
            output={"type": "spatial_result"},
        )


class LegacyPlanner:
    def plan(self, request):
        return TaskPlan(
            goal="legacy planner",
            steps=[PlanStep("schema", "get_dataset_schema", {"dataset": "roads"})],
            output={"type": "spatial_result"},
        )


class RecordingLLMClient:
    def __init__(self):
        self.messages = None

    def complete_json(self, messages, schema):
        self.messages = messages
        return {
            "goal": "inspect roads",
            "steps": [{"id": "schema", "tool": "get_dataset_schema", "args": {"dataset": "roads"}}],
            "output": {"type": "spatial_result"},
        }


def registry():
    return ToolRegistry.from_json(
        str(ROOT / "tools" / "schema" / "tool-definitions.json"), DemoSpatialAdapter()
    )


class M77ContextEngineeringTests(unittest.TestCase):
    def test_builder_is_bounded_and_redacts_sensitive_keys(self):
        packet = ContextBuilder(max_chars=512).build(
            request="查询" + "洪山区" * 500,
            resolved_request="查询" + "洪山区" * 500,
            session_id="session-1",
            workflow={"template_id": "demo", "api_key": "must-not-appear", "constraints": {"x": "y"}},
            available_tools=["tool-" + str(i) for i in range(100)],
        )
        self.assertLessEqual(len(packet.rendered), 512)
        self.assertEqual(packet.evidence["schema_version"], CONTEXT_SCHEMA_VERSION)
        self.assertTrue(packet.evidence["truncated"])
        self.assertNotIn("must-not-appear", packet.rendered)
        json.loads(packet.rendered)

    def test_runtime_passes_context_to_capable_planner_and_records_evidence(self):
        planner = ContextAwarePlanner()
        result = AgentRuntime(planner, registry()).run("查询道路数据", session_id="m77")
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(planner.context["schema_version"], CONTEXT_SCHEMA_VERSION)
        self.assertEqual(result.context_evidence["schema_version"], CONTEXT_SCHEMA_VERSION)
        self.assertNotIn("sections", result.context_evidence)

    def test_legacy_planner_remains_a_valid_harness_adapter(self):
        result = AgentRuntime(LegacyPlanner(), registry()).run("查询道路数据")
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertTrue(result.context_evidence["available"])

    def test_llm_planner_receives_context_as_separate_trusted_metadata(self):
        client = RecordingLLMClient()
        planner = LLMPlanner(client, registry().names)
        planner.plan(
            "查询道路数据",
            context={"schema_version": CONTEXT_SCHEMA_VERSION, "sections": {"request": {"original": "查询道路数据"}}},
        )
        self.assertIn("Trusted runtime context", client.messages[1]["content"])
        self.assertIn(CONTEXT_SCHEMA_VERSION, client.messages[1]["content"])

    def test_result_contract_exposes_only_context_evidence(self):
        result = AgentRuntime(ContextAwarePlanner(), registry()).run("查询道路数据")
        payload = result.to_dict()
        self.assertIn("context_evidence", payload)
        self.assertNotIn("sections", payload["context_evidence"])

    def test_console_surfaces_context_budget_evidence(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("const contextEvidence=envelope.context||data.context_evidence||{}", html)
        self.assertIn("上下文工程", html)

    def test_sqlite_recovery_preserves_context_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStateStore(str(Path(directory) / "runs.sqlite"))
            result = AgentRuntime(ContextAwarePlanner(), registry(), state_store=store).run(
                "查询道路数据", session_id="m77-sqlite"
            )
            restored = store.get(result.run_id)
            self.assertEqual(
                restored.context_evidence["request_sha256"],
                result.context_evidence["request_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
