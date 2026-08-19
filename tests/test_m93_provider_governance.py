import unittest
from pathlib import Path

from agent.errors import ToolError
from agent.models import PlanStep, TaskPlan
from agent.observability import CollectingEmitter
from agent.planner import RuleBasedPlanner
from agent.replanning import ReplanningPolicy
from agent.runtime import AgentRuntime
from agent.tool_provider import NativeToolProvider, ToolProviderError
from agent.tools import DemoSpatialAdapter, ToolRegistry


ROOT = Path(__file__).parents[1]


def echo_definitions():
    return {
        "echo": {
            "name": "echo",
            "description": "Bounded echo tool",
            "side_effect": "none",
            "requires_approval": True,
            "permissions": ["demo:read"],
            "data_dependencies": ["demo_dataset"],
            "timeout_seconds": 3,
            "input_schema": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "string"}},
                "additionalProperties": False,
            },
            "output_schema": {"type": "object"},
        }
    }


class EchoAdapter:
    def invoke(self, name, arguments):
        return {"echo": arguments["value"]}


class BrokenProvider:
    provider_id = "broken-provider"

    def definitions(self):
        return echo_definitions()

    def health(self):
        raise RuntimeError("https://secret.example.invalid/token")

    def invoke(self, name, arguments):
        raise ToolProviderError(
            "provider request failed",
            provider_id=self.provider_id,
            code="upstream_timeout",
            retryable=True,
        )


class EchoPlanner:
    def plan(self, request, context=None):
        return TaskPlan(
            goal="invoke echo",
            steps=[PlanStep("echo", "echo", {"value": "ok"}, [])],
            output={"type": "vector_result", "summary": True},
        )


class M93ProviderGovernanceTests(unittest.TestCase):
    def test_native_provider_reports_bounded_ready_health(self):
        registry = ToolRegistry.from_provider(
            NativeToolProvider(echo_definitions(), EchoAdapter())
        )

        health = registry.provider_health()

        self.assertEqual(health["schema_version"], "spatial-agent.tool-provider-health.v1")
        self.assertEqual(health["status"], "ready")
        self.assertEqual(health["provider_id"], "native")
        self.assertEqual([item["status"] for item in health["checks"]], ["passed", "passed"])

    def test_health_failure_is_safe_and_does_not_leak_provider_exception(self):
        health = ToolRegistry.from_provider(BrokenProvider()).provider_health()

        self.assertEqual(health["status"], "unavailable")
        self.assertEqual(health["reason_code"], "health_check_failed")
        self.assertNotIn("secret.example", str(health))

    def test_governance_summary_exposes_bounded_permission_and_data_metadata(self):
        registry = ToolRegistry.from_provider(
            NativeToolProvider(echo_definitions(), EchoAdapter())
        )

        governance = registry.governance_summary()
        tool = governance["tools"][0]

        self.assertEqual(governance["schema_version"], "spatial-agent.tool-governance.v1")
        self.assertEqual(tool["permissions"], ["demo:read"])
        self.assertEqual(tool["data_dependencies"], ["demo_dataset"])
        self.assertEqual(tool["timeout_seconds"], 3.0)
        self.assertEqual(governance["requires_approval_count"], 1)

    def test_provider_failure_preserves_machine_classification_at_registry_boundary(self):
        registry = ToolRegistry.from_provider(BrokenProvider())

        with self.assertRaises(ToolError) as context:
            registry.invoke("echo", {"value": "ok"})

        self.assertEqual(context.exception.category, "provider")
        self.assertEqual(context.exception.code, "upstream_timeout")
        self.assertTrue(context.exception.retryable)

    def test_runtime_plan_evidence_contains_health_and_governance(self):
        registry = ToolRegistry.from_json(
            str(ROOT / "tools" / "schema" / "tool-definitions.json"),
            DemoSpatialAdapter(),
        )

        result = AgentRuntime(RuleBasedPlanner(), registry).run("查询DEM栅格元数据")

        evidence = result.plan_evidence
        self.assertEqual(
            evidence["capability_catalog_tool_provider_health"]["status"],
            "ready",
        )
        self.assertEqual(
            evidence["capability_catalog_tool_governance"]["schema_version"],
            "spatial-agent.tool-governance.v1",
        )
        self.assertIn("capability_catalog", result.context_evidence["section_names"])

    def test_provider_failure_survives_runtime_step_result_and_observability(self):
        emitter = CollectingEmitter()
        registry = ToolRegistry.from_provider(BrokenProvider())
        result = AgentRuntime(
            EchoPlanner(),
            registry,
            replan_policy=ReplanningPolicy(limit=0),
            observability=emitter,
            allowed_permissions={"demo:read"},
            approved_tools={"echo"},
        ).run("调用 echo")

        self.assertEqual(result.status.value, "FAILED")
        self.assertEqual(result.error_category, "provider")
        self.assertEqual(result.steps[0].error_category, "provider")
        self.assertEqual(result.steps[0].error_code, "upstream_timeout")
        self.assertTrue(result.steps[0].retryable)
        step_events = [event for event in emitter.events if event["event"] == "step"]
        self.assertEqual(step_events[-1]["attributes"]["error_category"], "provider")
        self.assertNotIn("secret.example", str(result.to_dict()))
if __name__ == "__main__":
    unittest.main()
