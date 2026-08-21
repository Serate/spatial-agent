"""M154: workflow-aware, bounded planning repair diagnostics."""

import unittest

from agent.errors import ToolError
from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from agent.plan_quality import diagnose_plan, repair_context
from agent.plan_repair import PlanRepairEngine, PlanRepairInput
from agent.replanning import ReplanningPolicy
from agent.runtime import AgentRuntime
from agent.tools import ToolRegistry
from agent.workflow_templates import workflow_template_context_summary


def _template_context():
    return {"workflow_templates": workflow_template_context_summary(compact=True)}


def _plan_from_template():
    context = _template_context()["workflow_templates"]
    template = next(item for item in context["templates"] if item["id"] == "spatial_overview")
    steps = [
        PlanStep(
            item["id"],
            item["tool"],
            {key: None for key in item.get("arg_keys", [])},
            list(item.get("depends_on") or []),
        )
        for item in template["step_blueprint"]
    ]
    return TaskPlan("overview", steps, {"type": "spatial_overview_result"})


def _runtime_registry():
    names = {
        "get_dataset_health_report",
        "get_dataset_schema",
        "range_query",
        "get_zonal_raster_statistics",
        "get_zonal_slope_statistics",
        "get_zonal_land_use_distribution",
        "get_zonal_vector_summary",
    }
    definitions = {
        name: {
            "name": name,
            "input_schema": {"type": "object", "additionalProperties": True},
        }
        for name in names
    }
    return ToolRegistry(definitions, _Adapter())


class _Planner:
    def __init__(self, replacement):
        self.replacement = replacement
        self.contexts = []

    def plan(self, request, workflow=None, context=None):
        del request, workflow
        self.contexts.append(context)
        return self.replacement


class _Adapter:
    def invoke(self, name, arguments):
        raise AssertionError("execution is not part of this contract test")


class M154PlanQualityTests(unittest.TestCase):
    def test_diagnostic_reports_extra_steps_without_silent_deduplication(self):
        candidate = _plan_from_template()
        candidate = TaskPlan(
            candidate.goal,
            candidate.steps + [PlanStep("extra", "get_dataset_health_report", {})],
            candidate.output,
        )
        diagnostic = diagnose_plan(candidate, _template_context())

        self.assertTrue(diagnostic["available"])
        self.assertFalse(diagnostic["passed"])
        self.assertEqual(diagnostic["reason_code"], "workflow_blueprint_mismatch")
        self.assertIn("template_step_count", [item["code"] for item in diagnostic["issues"]])
        self.assertEqual(len(candidate.steps), 9)
        self.assertEqual(repair_context(diagnostic)["template_id"], "spatial_overview")

    def test_repair_receives_explicit_blueprint_and_accepts_exact_replacement(self):
        replacement = _plan_from_template()
        candidate = TaskPlan(
            "overview",
            replacement.steps[:2] + [PlanStep("extra", "range_query", {})],
            replacement.output,
        )
        planner = _Planner(replacement)
        engine = PlanRepairEngine(
            planner,
            ReplanningPolicy(limit=1),
            available_tools=lambda: [step.tool for step in replacement.steps] + ["range_query"],
            validate_plan=lambda plan, workflow: None,
            control_check=lambda run_id, deadline: None,
        )

        outcome = engine.repair(
            PlanRepairInput(
                request="overview",
                candidate=candidate,
                workflow=None,
                validation_error="workflow blueprint mismatch",
                capability_context=_template_context(),
            )
        )

        self.assertEqual(outcome.status, "repaired")
        self.assertEqual(planner.contexts[0]["workflow_repair"]["template_id"], "spatial_overview")
        self.assertEqual(planner.contexts[0]["workflow_repair"]["expected_step_count"], 8)

    def test_execution_replan_receives_blueprint_and_accepts_exact_merge(self):
        original = _plan_from_template()
        replacement = TaskPlan(
            "continue overview",
            original.steps[2:],
            original.output,
        )
        planner = _Planner(replacement)
        runtime = AgentRuntime(
            planner,
            _runtime_registry(),
            replan_policy=ReplanningPolicy(limit=1),
        )
        result = AgentRunResult(
            "run-1",
            RunStatus.EXECUTING,
            "overview",
            plan=original,
            steps=[
                StepRun(step.id, step.tool, step.args, list(step.depends_on))
                for step in original.steps
            ],
        )
        result.steps[1].status = "FAILED"
        result.steps[1].error_category = "tool_gate"

        accepted = runtime._try_replan(
            result,
            "overview",
            1,
            result.steps[1],
            original.steps[1],
            ToolError("tool gate"),
            {"dataset-health"},
            {},
            0,
            None,
        )

        self.assertTrue(accepted)
        self.assertEqual(
            planner.contexts[0]["workflow_repair"]["template_id"],
            "spatial_overview",
        )
        self.assertTrue(diagnose_plan(result.plan, _template_context())["passed"])

    def test_execution_replan_rejects_blueprint_mismatch_after_merge(self):
        original = _plan_from_template()
        duplicate = PlanStep(
            "duplicate-health",
            "get_dataset_health_report",
            {"dataset": "all", "max_files": 10},
            [],
        )
        replacement = TaskPlan(
            "invalid overview repair",
            [duplicate] + original.steps[3:],
            original.output,
        )
        runtime = AgentRuntime(
            _Planner(replacement),
            _runtime_registry(),
            replan_policy=ReplanningPolicy(limit=1),
        )
        result = AgentRunResult(
            "run-2",
            RunStatus.EXECUTING,
            "overview",
            plan=original,
            steps=[
                StepRun(step.id, step.tool, step.args, list(step.depends_on))
                for step in original.steps
            ],
        )
        result.steps[1].status = "FAILED"
        result.steps[1].error_category = "tool_gate"

        accepted = runtime._try_replan(
            result,
            "overview",
            1,
            result.steps[1],
            original.steps[1],
            ToolError("tool gate"),
            {"dataset-health"},
            {},
            0,
            None,
        )

        self.assertFalse(accepted)
        self.assertEqual(len(result.replan_events), 0)


if __name__ == "__main__":
    unittest.main()
