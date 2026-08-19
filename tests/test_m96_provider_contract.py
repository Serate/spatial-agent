import unittest

from agent.errors import ToolError
from agent.models import PlanStep, TaskPlan
from agent.runtime import AgentRuntime
from agent.runtime_capabilities import tool_provider_snapshot
from agent.tool_provider import TOOL_PROVIDER_CONTRACT_SCHEMA
from agent.tools import ToolRegistry


def echo_definitions(**overrides):
    definition = {
        "name": "echo",
        "description": "A bounded provider replay tool",
        "side_effect": "none",
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
    definition.update(overrides)
    return {"echo": definition}


class ExternalReplayProvider:
    provider_id = "external-replay"

    def __init__(self, definitions=None):
        self._definitions = definitions or echo_definitions()
        self.calls = []

    def definitions(self):
        return self._definitions

    def health(self):
        return {
            "status": "ready",
            "checks": [{"name": "replay", "status": "passed"}],
        }

    def invoke(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return {"echo": "external:" + arguments["value"]}


class EchoPlanner:
    def plan(self, request, context=None):
        return TaskPlan(
            goal="invoke provider replay",
            steps=[PlanStep("echo", "echo", {"value": "ok"}, [])],
            output={"type": "vector_result", "summary": True},
        )


class M96ProviderContractTests(unittest.TestCase):
    def test_registry_rejects_malformed_provider_catalog_before_runtime(self):
        with self.assertRaises(ToolError) as context:
            ToolRegistry.from_provider(
                ExternalReplayProvider(
                    {"echo": {"name": "echo", "input_schema": {"type": "array"}}}
                )
            )

        self.assertIn("object schema", str(context.exception))

    def test_registry_rejects_catalog_key_name_mismatch(self):
        with self.assertRaises(ToolError) as context:
            ToolRegistry.from_provider(
                ExternalReplayProvider(
                    {"echo": {"name": "other", "input_schema": {"type": "object"}}}
                )
            )

        self.assertIn("does not match catalogue key", str(context.exception))

    def test_external_provider_runs_through_same_runtime_contract(self):
        provider = ExternalReplayProvider()
        registry = ToolRegistry.from_provider(provider)
        result = AgentRuntime(
            EchoPlanner(),
            registry,
            allowed_permissions={"demo:read"},
        ).run("调用外部回放工具")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.steps[0].result, {"echo": "external:ok"})
        self.assertEqual(provider.calls, [("echo", {"value": "ok"})])
        health = result.plan_evidence["capability_catalog_tool_provider_health"]
        self.assertEqual(health["provider_id"], "external-replay")
        self.assertEqual(
            health["definition_contract"]["schema_version"],
            TOOL_PROVIDER_CONTRACT_SCHEMA,
        )
        self.assertEqual(health["definition_contract"]["status"], "valid")
        self.assertEqual(result.steps[0].governance["permissions"], ["demo:read"])
        self.assertEqual(result.steps[0].governance["data_dependencies"], ["demo_dataset"])

    def test_native_capability_snapshot_exposes_valid_provider_contract(self):
        snapshot = tool_provider_snapshot()
        contract = snapshot["tool_provider_health"]["definition_contract"]

        self.assertEqual(contract["schema_version"], TOOL_PROVIDER_CONTRACT_SCHEMA)
        self.assertEqual(contract["status"], "valid")
        self.assertEqual(contract["tool_count"], snapshot["tool_provider"]["tool_count"])


if __name__ == "__main__":
    unittest.main()
