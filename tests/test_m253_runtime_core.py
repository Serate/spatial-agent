import unittest

from agent.models import PlanStep, StepRun, TaskPlan
from agent.context_engineering import ContextPacket
from agent.errors import ClarificationNeeded, ToolError
from agent.runtime import _resolve_result_references
from agent.runtime_core.projection import (
    compact_workflow_templates,
    plan_dag,
    plan_to_dict,
)
from agent.runtime_core.planning import invoke_planner, validate_plan
from agent.runtime_core.execution import StepExecutionHooks, block_remaining_steps, execute_step


class M253RuntimeCoreProjectionTests(unittest.TestCase):
    def test_plan_projection_is_domain_neutral_and_bounded(self):
        plan = TaskPlan(
            goal="组合分析",
            steps=[
                PlanStep("source", "inspect", {"dataset": "roads"}),
                PlanStep("result", "summarize", {}, ["source"]),
            ],
            output={"type": "composite_result"},
            assumptions=["仅使用已注册工具"],
        )

        self.assertEqual(plan_to_dict(plan)["steps"][1]["depends_on"], ["source"])
        dag = plan_dag(plan)
        self.assertEqual(dag["node_count"], 2)
        self.assertEqual(dag["edges"], [{"from": "source", "to": "result"}])

    def test_workflow_context_keeps_only_selected_templates(self):
        templates = {
            "templates": [{"id": "roads"}, {"id": "water"}, {"id": "land"}],
            "schema_version": "test",
        }
        compact = compact_workflow_templates(
            templates,
            {"workflow_template_id": "water"},
        )

        self.assertEqual([item["id"] for item in compact["templates"]], ["water"])
        self.assertEqual(compact["omitted_count"], 2)

    def test_legacy_runtime_reference_helper_uses_same_contract(self):
        self.assertEqual(
            _resolve_result_references(
                {"value": {"$from": "source", "path": "nested.value"}},
                {"source": {"nested": {"value": "ok"}}},
            ),
            {"value": "ok"},
        )

    def test_planner_seam_supports_legacy_and_context_aware_planners(self):
        plan = TaskPlan("目标", [PlanStep("one", "inspect", {})])

        class LegacyPlanner:
            def plan(self, request):
                self.request = request
                return plan

        class ContextPlanner:
            def plan(self, request, *, workflow=None, context=None):
                self.payload = (request, workflow, context)
                return plan

        packet = ContextPacket(
            payload={"sections": {"request": {"original": "请求"}}},
            rendered="{}",
            evidence={},
        )
        self.assertIs(invoke_planner(LegacyPlanner(), "请求", None, packet), plan)
        planner = ContextPlanner()
        self.assertIs(invoke_planner(planner, "请求", {"template_id": "x"}, packet), plan)
        self.assertEqual(planner.payload[1], {"template_id": "x"})
        self.assertEqual(planner.payload[2], packet.payload)

    def test_plan_validation_seam_preserves_dependency_errors(self):
        with self.assertRaises(ToolError):
            validate_plan(
                TaskPlan("目标", [PlanStep("one", "missing", {})]),
                {"inspect"},
                4,
            )
        with self.assertRaises(ClarificationNeeded):
            validate_plan(TaskPlan("目标", []), {"inspect"}, 4)

    def test_execution_seam_retries_registry_failure_and_emits_terminal_state(self):
        class Registry:
            def __init__(self):
                self.calls = 0

            def governance_for(self, tool):
                return {"name": tool}

            def timeout_seconds(self, tool):
                return None

            def invoke(self, tool, arguments, timeout_seconds=None):
                self.calls += 1
                if self.calls == 1:
                    raise ToolError("temporary", retryable=True)
                return {"ok": True, "arguments": arguments}

        registry = Registry()
        events = []
        hooks = StepExecutionHooks(
            registry=registry,
            max_retries=1,
            preflight=lambda tool, args, results: None,
            control_check=lambda run_id, deadline: None,
            emit_step=lambda run_id, step_run: events.append(step_run.status),
            now=lambda: "2026-01-01T00:00:00Z",
        )
        step_run = StepRun("one", "inspect", {})

        execute_step(
            hooks,
            "run-1",
            None,
            step_run,
            PlanStep("one", "inspect", {}),
            set(),
            {},
        )

        self.assertEqual(registry.calls, 2)
        self.assertEqual(step_run.status, "COMPLETED")
        self.assertEqual(step_run.attempts, 2)
        self.assertEqual(events, ["COMPLETED"])

    def test_execution_seam_blocks_only_pending_steps(self):
        steps = [
            StepRun("done", "inspect", {}, status="COMPLETED"),
            StepRun("failed", "inspect", {}, status="FAILED"),
            StepRun("pending", "inspect", {}),
        ]
        block_remaining_steps(steps, 1, "failed", "backend")
        self.assertEqual(steps[0].status, "COMPLETED")
        self.assertEqual(steps[1].status, "FAILED")
        self.assertEqual(steps[2].status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
