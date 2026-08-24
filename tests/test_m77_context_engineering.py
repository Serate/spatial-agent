import json
import tempfile
import unittest
from pathlib import Path

from tests.console_source import read_console_source

from agent.context_engineering import CONTEXT_SCHEMA_VERSION, ContextBuilder
from agent.domain_contract import planner_guidance
from agent.llm_planner import LLMPlanner
from agent.models import PlanStep, TaskPlan
from agent.runtime import AgentRuntime
from agent.sqlite_store import SQLiteStateStore
from agent.tools import DemoSpatialAdapter, ToolRegistry
from agent.workflow_templates import workflow_template_context_summary
from result_contract import build_result_contract
from domains.gis.domain import GIS_DOMAIN_PACK


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


class SpatialContextPlanner:
    def __init__(self):
        self.context = None

    def plan(self, request, context=None):
        self.context = context
        return TaskPlan(
            goal="inspect spatial context",
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
            workflow_templates=workflow_template_context_summary(),
        )
        self.assertLessEqual(len(packet.rendered), 512)
        self.assertEqual(packet.evidence["schema_version"], CONTEXT_SCHEMA_VERSION)
        self.assertTrue(packet.evidence["truncated"])
        self.assertNotIn("must-not-appear", packet.rendered)
        json.loads(packet.rendered)

    def test_builder_includes_workflow_template_context_when_budget_allows(self):
        packet = ContextBuilder(max_chars=12000).build(
            request="查询DEM栅格元数据",
            available_tools=registry().names,
            workflow_templates=workflow_template_context_summary(),
        )

        templates = packet.payload["sections"]["workflow_templates"]
        self.assertIn("workflow_templates", packet.evidence["section_names"])
        self.assertEqual(templates["schema_version"], "spatial-agent.workflow_templates.v1")
        self.assertTrue(any(item["id"] == "raster_metadata" for item in templates["templates"]))

    def test_runtime_passes_context_to_capable_planner_and_records_evidence(self):
        planner = ContextAwarePlanner()
        result = AgentRuntime(planner, registry()).run("查询道路数据", session_id="m77")
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(planner.context["schema_version"], CONTEXT_SCHEMA_VERSION)
        self.assertIn("workflow_templates", planner.context["sections"])
        self.assertIn("capability_discovery", planner.context["sections"])
        self.assertIn("capability_catalog", planner.context["sections"])
        self.assertEqual(result.context_evidence["schema_version"], CONTEXT_SCHEMA_VERSION)
        self.assertEqual(result.plan_evidence["planner_kind"], "ContextAwarePlanner")
        self.assertTrue(result.plan_evidence["template_context_available"])
        self.assertTrue(result.plan_evidence["capability_discovery_available"])
        self.assertTrue(result.plan_evidence["capability_catalog_available"])
        self.assertEqual(result.plan_evidence["capability_catalog_environment"], "unknown")
        self.assertIn("vector_query", result.plan_evidence["capability_candidate_ids"])
        self.assertNotIn("sections", result.context_evidence)

    def test_runtime_adds_structured_spatial_request_facts_to_context(self):
        planner = SpatialContextPlanner()
        result = AgentRuntime(planner, registry()).run(
            "请对洪山区进行综合空间分析，统计DEM高程和坡度不超过20度"
        )
        spatial_request = planner.context["sections"]["spatial_request"]
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(spatial_request["admin_name"], "洪山区")
        self.assertIn("elevation", spatial_request["tasks"])
        self.assertEqual(spatial_request["constraints"]["slope_max"], 20.0)
        self.assertNotIn("text", spatial_request)
        capability_discovery = planner.context["sections"]["capability_discovery"]
        self.assertEqual(
            capability_discovery["schema_version"],
            "spatial-agent.capability-discovery.v1",
        )
        self.assertIn("zonal_raster_statistics", capability_discovery["candidate_ids"])
        capability_catalog = planner.context["sections"]["capability_catalog"]
        self.assertEqual(
            capability_catalog["schema_version"],
            "spatial-agent.capability-catalog-context.v1",
        )
        self.assertIn("get_zonal_raster_statistics", capability_catalog["tool_schemas"])

    def test_legacy_planner_remains_a_valid_harness_adapter(self):
        result = AgentRuntime(LegacyPlanner(), registry()).run("查询道路数据")
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertTrue(result.context_evidence["available"])

    def test_llm_planner_receives_context_as_separate_trusted_metadata(self):
        client = RecordingLLMClient()
        planner = LLMPlanner(
            client,
            registry().names,
            planner_guidance=planner_guidance(GIS_DOMAIN_PACK),
        )
        planner.plan(
            "查询道路数据",
            context={
                "schema_version": CONTEXT_SCHEMA_VERSION,
                "sections": {
                    "request": {"original": "查询道路数据"},
                    "workflow_templates": workflow_template_context_summary(),
                },
            },
        )
        self.assertIn("Trusted runtime context", client.messages[1]["content"])
        self.assertIn(CONTEXT_SCHEMA_VERSION, client.messages[1]["content"])
        self.assertIn("raster_metadata", client.messages[1]["content"])
        self.assertIn("spatial_analysis_result", client.messages[0]["content"])
        self.assertIn("Domain-owned planner guidance", client.messages[0]["content"])
        self.assertIn("workflow_templates", client.messages[0]["content"])
        self.assertIn("capability_catalog", client.messages[0]["content"])

    def test_result_contract_exposes_only_context_evidence(self):
        result = AgentRuntime(ContextAwarePlanner(), registry()).run("查询道路数据")
        payload = result.to_dict()
        self.assertIn("context_evidence", payload)
        self.assertIn("plan_evidence", payload)
        self.assertNotIn("sections", payload["context_evidence"])
        self.assertNotIn("sections", payload["plan_evidence"])
        contract = build_result_contract({**payload, "result_type": result.plan.output["type"]})
        self.assertEqual(contract["planning"]["planner_kind"], "ContextAwarePlanner")

    def test_console_surfaces_context_budget_evidence(self):
        html = read_console_source(ROOT)
        self.assertIn("const contextEvidence=envelope.context||data.context_evidence||{}", html)
        self.assertIn("const planEvidence=envelope.planning||data.plan_evidence||{}", html)
        self.assertIn("上下文工程", html)
        self.assertIn("计划来源", html)

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
            self.assertEqual(
                restored.plan_evidence["planner_kind"],
                result.plan_evidence["planner_kind"],
            )


if __name__ == "__main__":
    unittest.main()
