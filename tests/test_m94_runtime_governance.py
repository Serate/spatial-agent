import json
import time
import unittest
from pathlib import Path

from agent.errors import ToolError
from agent.models import PlanStep, TaskPlan
from agent.runtime import AgentRuntime
from agent.runtime_capabilities import runtime_capability_snapshot, tool_provider_snapshot
from agent.tools import ToolRegistry


class FixedPlanner:
    def __init__(self, tool, arguments=None, steps=None):
        self.tool = tool
        self.arguments = arguments or {}
        self.steps = steps

    def plan(self, request):
        steps = self.steps or [PlanStep("step", self.tool, self.arguments, [])]
        return TaskPlan("governance test", steps, {"type": "governance_test_result"})


class RecordingAdapter:
    def __init__(self, *, health=None, delay=0):
        self.calls = []
        self.health = health
        self.delay = delay

    def invoke(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if self.delay:
            time.sleep(self.delay)
        if name == "health":
            return self.health
        return {"ok": True}


def definitions(*, permission="demo:read", dependency=None, approval=False, timeout=None):
    result = {
        "probe": {
            "name": "probe",
            "permissions": [permission] if permission else [],
            "data_dependencies": [dependency] if dependency else [],
            "requires_approval": approval,
            "input_schema": {
                "type": "object",
                "properties": {"dataset": {"type": "string"}},
                "additionalProperties": False,
            },
        }
    }
    if timeout is not None:
        result["probe"]["timeout_seconds"] = timeout
    return result


class M94RuntimeGovernanceTests(unittest.TestCase):
    def test_provider_snapshot_is_bounded_and_does_not_execute_tools(self):
        snapshot = tool_provider_snapshot()

        self.assertEqual(snapshot["tool_provider"]["id"], "native")
        self.assertEqual(snapshot["tool_provider_health"]["status"], "ready")
        self.assertGreater(snapshot["tool_provider"]["tool_count"], 0)
        self.assertIn("tool_governance", snapshot)
        self.assertEqual(snapshot["tool_governance"]["returned_tool_count"], 14)

    def test_runtime_capability_snapshot_exposes_provider_evidence(self):
        snapshot = runtime_capability_snapshot(max_files=1)

        self.assertIn("tool_provider", snapshot)
        self.assertIn("tool_provider_health", snapshot)
        self.assertIn("tool_governance", snapshot)
        self.assertEqual(snapshot["tool_provider_health"]["provider_id"], "native")

    def test_permission_gate_runs_before_adapter(self):
        adapter = RecordingAdapter()
        registry = ToolRegistry(definitions(permission="demo:write"), adapter)
        result = AgentRuntime(
            FixedPlanner("probe"),
            registry,
            allowed_permissions={"demo:read"},
        ).run("调用探针")

        self.assertEqual(result.status.value, "FAILED")
        self.assertEqual(result.steps[0].error_code, "permission_denied")
        self.assertEqual(adapter.calls, [])

    def test_approval_gate_runs_before_adapter(self):
        adapter = RecordingAdapter()
        registry = ToolRegistry(definitions(permission=None, approval=True), adapter)
        result = AgentRuntime(FixedPlanner("probe"), registry).run("调用探针")

        self.assertEqual(result.status.value, "FAILED")
        self.assertEqual(result.steps[0].error_code, "approval_required")
        self.assertEqual(adapter.calls, [])

    def test_strict_dependency_mode_requires_health_evidence(self):
        adapter = RecordingAdapter()
        registry = ToolRegistry(definitions(permission=None, dependency="$dataset"), adapter)
        result = AgentRuntime(
            FixedPlanner("probe", {"dataset": "demo"}),
            registry,
            require_dependency_evidence=True,
        ).run("查询 demo")

        self.assertEqual(result.status.value, "FAILED")
        self.assertEqual(result.steps[0].error_code, "dependency_evidence_required")
        self.assertEqual(adapter.calls, [])

    def test_health_evidence_blocks_unavailable_declared_dependency(self):
        adapter = RecordingAdapter(
            health={
                "capabilities": [],
                "datasets": [{"dataset": "demo", "status": "unavailable"}],
            }
        )
        defs = {
            "health": {
                "name": "health",
                "input_schema": {"type": "object", "additionalProperties": False},
            },
            **definitions(permission=None, dependency="$dataset"),
        }
        planner = FixedPlanner(
            "probe",
            {"dataset": "demo"},
            [
                PlanStep("health", "health", {}, []),
                PlanStep("probe", "probe", {"dataset": "demo"}, ["health"]),
            ],
        )
        result = AgentRuntime(
            planner,
            ToolRegistry(defs, adapter),
            require_dependency_evidence=True,
        ).run("查询 demo")

        self.assertEqual(result.status.value, "FAILED")
        self.assertEqual(result.steps[0].status, "COMPLETED")
        self.assertEqual(result.steps[1].error_code, "data_unavailable")
        self.assertEqual([call[0] for call in adapter.calls], ["health"])

    def test_declared_tool_timeout_is_enforced_at_registry_dispatch(self):
        adapter = RecordingAdapter(delay=0.15)
        registry = ToolRegistry(
            definitions(permission=None, timeout=0.03),
            adapter,
        )

        with self.assertRaises(ToolError) as context:
            registry.invoke(
                "probe",
                {},
                timeout_seconds=registry.timeout_seconds("probe"),
            )

        self.assertEqual(context.exception.code, "tool_timeout")
        self.assertFalse(context.exception.retryable)
        self.assertEqual(len(adapter.calls), 1)

    def test_builtin_manifest_declares_timeout_for_every_tool(self):
        path = Path(__file__).parents[1] / "tools" / "schema" / "tool-definitions.json"
        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(payload["tools"])
        self.assertTrue(all(item.get("timeout_seconds", 0) > 0 for item in payload["tools"]))


if __name__ == "__main__":
    unittest.main()
