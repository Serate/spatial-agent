import unittest

from agent.domain_contract import DOMAIN_DISCOVERY_SCHEMA_VERSION
from agent.capability_catalog import capability_catalog
from agent.models import TaskPlan
from agent.runtime import AgentRuntime
from agent.tools import DemoSpatialAdapter, ToolRegistry


class FakeDomainPack:
    domain_id = "text-analytics"

    def capability_catalog(self, *, environment="unknown"):
        return {
            "domain_id": self.domain_id,
            "version": "text-analytics.v1",
            "environment": environment,
            "capabilities": [
                {
                    "id": "text_summary",
                    "label": "文本摘要",
                    "datasets": [],
                    "tools": [],
                    "result_types": ["text_summary_result"],
                    "environments": ["memory"],
                    "geometry": "none",
                }
            ],
            "dataset_tools": {},
            "available_dataset_tools": {},
            "dataset_groups": {},
            "workflow_templates": {},
        }

    def discover(self, request, request_facts):
        return {
            "schema_version": DOMAIN_DISCOVERY_SCHEMA_VERSION,
            "available": True,
            "selected_capability_id": "text_summary",
            "candidate_ids": ["text_summary"],
            "candidate_count": 1,
            "signals": ["summary"],
            "tasks": [],
            "constraints": [],
        }


class CapturingPlanner:
    def __init__(self):
        self.context = None

    def plan(self, request, context=None, workflow=None):
        self.context = context
        return TaskPlan(
            goal="answer a text request",
            steps=[],
            output={"type": "direct_answer", "message": "已通过文本领域能力处理。"},
        )


class M112DomainPackTests(unittest.TestCase):
    def test_catalog_builder_accepts_non_gis_definitions(self):
        catalog = capability_catalog(
            domain_id="text-analytics",
            capability_definitions=(
                {
                    "id": "text_summary",
                    "label": "文本摘要",
                    "datasets": ["documents"],
                    "tools": ["summarize_text"],
                    "result_types": ["text_summary_result"],
                    "environments": ["memory"],
                    "geometry": "none",
                },
            ),
            dataset_tool_capabilities={"documents": ["summarize_text"]},
            dataset_groups={"core": ("documents",)},
            workflow_templates={},
            analysis_ready_capability_ids=(),
        )

        self.assertEqual(catalog["domain_id"], "text-analytics")
        self.assertEqual([item["id"] for item in catalog["capabilities"]], ["text_summary"])
        self.assertEqual(catalog["dataset_tools"], {"documents": ["summarize_text"]})
        self.assertEqual(catalog["workflow_templates"], {})

    def test_runtime_accepts_non_gis_domain_pack(self):
        planner = CapturingPlanner()
        registry = ToolRegistry.from_json(
            "tools/schema/tool-definitions.json",
            DemoSpatialAdapter(),
        )
        runtime = AgentRuntime(planner, registry, domain_pack=FakeDomainPack())

        result = runtime.run("概括这段文本")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(planner.context["sections"]["capability_catalog"]["domain_id"], "text-analytics")
        self.assertEqual(
            planner.context["sections"]["capability_discovery"]["schema_version"],
            DOMAIN_DISCOVERY_SCHEMA_VERSION,
        )
        self.assertEqual(planner.context["sections"]["workflow_templates"], {})
        self.assertTrue(result.plan_evidence["capability_discovery_available"])
        self.assertEqual(result.plan_evidence["selected_capability_id"], "text_summary")

    def test_default_runtime_domain_remains_gis_compatible(self):
        planner = CapturingPlanner()
        registry = ToolRegistry.from_json(
            "tools/schema/tool-definitions.json",
            DemoSpatialAdapter(),
        )
        runtime = AgentRuntime(planner, registry)

        runtime.run("概括这段文本")

        self.assertEqual(planner.context["sections"]["capability_catalog"]["domain_id"], "gis")


if __name__ == "__main__":
    unittest.main()
