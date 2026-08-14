import unittest

from agent.errors import ToolError
from agent.llm_planner import LLMPlanner
from agent.models import PlanStep, TaskPlan
from agent.replanning import (
    ReplanningPolicy,
    build_replan_event,
    failure_category,
    merge_replanned_plan,
    replan_limit,
    rule_replan_plan,
)
from agent.runtime import AgentRuntime
from agent.tools import ToolRegistry


class DowngradePlanner:
    """Rule-style planner that can produce a replacement plan on demand."""

    def __init__(self, replacement=None):
        self._replacement = replacement
        self.replan_calls = 0

    def plan(self, request, context=None):
        if context and context.get("feedback") and self._replacement is not None:
            self.replan_calls += 1
            return self._replacement
        return TaskPlan(
            goal="exercise replanning",
            steps=[
                PlanStep("first", "make_value", {}, []),
                PlanStep("second", "fail_value", {}, ["first"]),
                PlanStep("third", "use_value", {}, ["second"]),
            ],
        )


class ReplanAdapter:
    def __init__(self):
        self.calls = {}

    def invoke(self, name, arguments):
        self.calls[name] = self.calls.get(name, 0) + 1
        if name == "make_value":
            return {"value": "retained"}
        if name == "fail_value":
            raise ToolError("simulated backend failure")
        if name == "use_value":
            return {"ok": True}
        if name == "recover_value":
            return {"value": "recovered"}
        if name == "get_dataset_health_report":
            return {"dataset": "all", "status": "ready", "capabilities": []}
        if name == "get_zonal_slope_statistics":
            return {"admin_name": "洪山区", "statistics": {"mean": 10.0}}
        if name == "get_zonal_land_use_distribution":
            return {"admin_name": "洪山区", "distribution": {"forest": 0.5}}
        raise AssertionError("unexpected tool: " + name)


def registry(tools):
    definitions = {
        name: {
            "name": name,
            "input_schema": {"type": "object", "additionalProperties": True},
        }
        for name in tools
    }
    adapter = ReplanAdapter()
    return ToolRegistry(definitions, adapter), adapter


def replacement_plan():
    return TaskPlan(
        goal="recover with a replacement step",
        steps=[
            PlanStep("recover", "recover_value", {}, ["first"]),
            PlanStep("final", "use_value", {}, ["recover"]),
        ],
    )


class M80ReplanningPolicyTests(unittest.TestCase):
    def test_should_replan_only_for_failed_steps_within_budget(self):
        policy = ReplanningPolicy(limit=1)
        self.assertTrue(policy.should_replan(replan_count=0, step_status="FAILED", step_error="boom"))
        self.assertFalse(policy.should_replan(replan_count=1, step_status="FAILED", step_error="boom"))
        self.assertFalse(policy.should_replan(replan_count=0, step_status="COMPLETED", step_error=None))
        self.assertFalse(policy.should_replan(replan_count=0, step_status="CANCELLED", step_error="stop"))

    def test_replan_limit_env_parsing(self):
        self.assertEqual(replan_limit(), 1)
        with self.assertRaises(ValueError):
            ReplanningPolicy(limit=-1)

    def test_failure_category_taxonomy(self):
        self.assertEqual(failure_category("像元级对齐门控阻止工具"), "tool_gate")
        self.assertEqual(failure_category("unknown tool: x"), "tool_validation")
        self.assertEqual(failure_category("result reference source is not complete"), "reference")
        self.assertEqual(failure_category("backend exploded"), "backend_execution")
        self.assertEqual(failure_category(None), "unknown")

    def test_merge_replanned_plan_renamespaces_and_rewrites_deps(self):
        original = TaskPlan(
            "orig",
            [
                PlanStep("first", "make_value", {}, []),
                PlanStep("second", "fail_value", {}, ["first"]),
                PlanStep("third", "use_value", {}, ["second"]),
            ],
        )
        replacement = TaskPlan(
            "recover",
            [
                PlanStep("recover", "recover_value", {}, ["first"]),
                PlanStep("final", "use_value", {}, ["recover"]),
            ],
        )
        merged = merge_replanned_plan(original, replacement, failed_step_id="second")
        ids = [step.id for step in merged.steps]
        # Original steps up to the failed one survive; "third" is dropped.
        self.assertEqual(ids[:2], ["first", "second"])
        self.assertNotIn("third", ids)
        # Replacement ids that do not collide keep their names.
        self.assertIn("recover", ids)
        self.assertIn("final", ids)
        replan_recover = next(step for step in merged.steps if step.id == "recover")
        self.assertEqual(replan_recover.depends_on, ["first"])
        replan_final = next(step for step in merged.steps if step.id == "final")
        self.assertEqual(replan_final.depends_on, ["recover"])

    def test_merge_renamespaces_colliding_replacement_ids(self):
        original = TaskPlan(
            "orig",
            [
                PlanStep("first", "make_value", {}, []),
                PlanStep("second", "fail_value", {}, ["first"]),
                PlanStep("recover", "old_value", {}, ["second"]),
            ],
        )
        replacement = TaskPlan(
            "recover",
            [
                PlanStep("recover", "recover_value", {}, ["first"]),
            ],
        )
        merged = merge_replanned_plan(original, replacement, failed_step_id="second")
        ids = [step.id for step in merged.steps]
        # Original "recover" was dropped (it depended on the failed step);
        # the replacement "recover" collides with nothing kept, so it keeps its id.
        self.assertEqual(ids, ["first", "second", "recover"])
        replan = next(step for step in merged.steps if step.id == "recover")
        self.assertEqual(replan.tool, "recover_value")
        self.assertEqual(replan.depends_on, ["first"])

    def test_build_replan_event_is_bounded(self):
        event = build_replan_event(
            failed_step_id="second",
            failed_tool="fail_value",
            failure_category="backend_execution",
            new_step_ids=["a", "b"],
            latency_ms=12.5,
        )
        self.assertEqual(event["failed_step_id"], "second")
        self.assertEqual(event["replanned_step_ids"], ["a", "b"])
        self.assertEqual(event["failure_category"], "backend_execution")
        self.assertNotIn("error", event)


class M80RuntimeReplanningTests(unittest.TestCase):
    def test_failed_step_triggers_replan_and_run_completes(self):
        reg, adapter = registry(
            ("make_value", "fail_value", "use_value", "recover_value")
        )
        runtime = AgentRuntime(
            DowngradePlanner(replacement=replacement_plan()),
            reg,
            max_retries=0,
            replan_policy=ReplanningPolicy(limit=1),
        )
        result = runtime.run("recover me")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.steps[0].status, "COMPLETED")
        self.assertEqual(result.steps[1].status, "FAILED")
        # Original third step was dropped; two replanned steps follow.
        self.assertEqual(len(result.steps), 4)
        self.assertEqual([step.tool for step in result.steps[2:]], ["recover_value", "use_value"])
        self.assertEqual(adapter.calls["recover_value"], 1)
        self.assertEqual(adapter.calls["use_value"], 1)
        self.assertEqual(len(result.replan_events), 1)
        event = result.replan_events[0]
        self.assertEqual(event["failed_step_id"], "second")
        self.assertEqual(len(event["replanned_step_ids"]), 2)

    def test_replan_budget_exhausted_fails_fast(self):
        reg, adapter = registry(
            ("make_value", "fail_value", "use_value", "recover_value")
        )
        runtime = AgentRuntime(
            DowngradePlanner(replacement=replacement_plan()),
            reg,
            max_retries=0,
            replan_policy=ReplanningPolicy(limit=0),
        )
        result = runtime.run("recover me")

        self.assertEqual(result.status.value, "FAILED")
        self.assertEqual(len(result.replan_events), 0)
        self.assertEqual(result.steps[2].status, "BLOCKED")
        self.assertEqual(adapter.calls.get("recover_value", 0), 0)

    def test_rule_replan_downgrades_constrained_to_plain(self):
        failed = {
            "id": "constrained-buildability",
            "tool": "get_zonal_constrained_buildability_analysis",
            "args": {
                "admin_name": {"$from": "filter-admin", "path": "first_name"},
                "road_distance_m": 500.0,
                "exclude_water": True,
            },
            "error_category": "tool_gate",
        }
        plan = rule_replan_plan(failed, {})
        self.assertEqual(plan.steps[-1].tool, "get_zonal_buildability_analysis")
        self.assertNotIn("road_distance_m", plan.steps[-1].args)
        self.assertEqual(plan.output["type"], "buildability_result")

    def test_rule_replan_downgrades_buildability_to_slope_and_landuse(self):
        failed = {
            "id": "buildability",
            "tool": "get_zonal_buildability_analysis",
            "args": {"admin_name": "洪山区", "max_files": 10},
            "error_category": "tool_gate",
        }
        plan = rule_replan_plan(failed, {})
        tools = [step.tool for step in plan.steps]
        self.assertIn("get_zonal_slope_statistics", tools)
        self.assertIn("get_zonal_land_use_distribution", tools)
        self.assertEqual(plan.output["type"], "terrain_land_use_analysis_result")

    def test_rule_replan_falls_back_to_health_summary(self):
        failed = {
            "id": "random-step",
            "tool": "some_tool",
            "args": {},
            "error_category": "backend_execution",
        }
        plan = rule_replan_plan(failed, {})
        self.assertEqual([step.tool for step in plan.steps], ["get_dataset_health_report"])
        self.assertEqual(plan.output["type"], "dataset_health_result")

    def test_rule_planner_runtime_replans_with_downgrade(self):
        reg, adapter = registry(
            (
                "get_dataset_health_report",
                "get_zonal_slope_statistics",
                "get_zonal_land_use_distribution",
                "fail_tool",
            )
        )

        class RuleLikePlanner:
            capability_rules = ["fake-rule"]

            def plan(self, request, context=None):
                return TaskPlan(
                    "exercise",
                    [
                        PlanStep("health", "get_dataset_health_report", {"dataset": "all", "max_files": 10}, []),
                        PlanStep("broken", "fail_tool", {"admin_name": "洪山区"}, ["health"]),
                    ],
                )

        runtime = AgentRuntime(
            RuleLikePlanner(),
            reg,
            max_retries=0,
            replan_policy=ReplanningPolicy(limit=1),
        )
        result = runtime.run("analyze")
        # Duck-typed rule path: unknown tool failure falls back to the health
        # summary plan, so the run completes with the degraded replacement.
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(len(result.replan_events), 1)
        self.assertEqual(result.replan_events[0]["failed_tool"], "fail_tool")
        tools = [step.tool for step in result.steps]
        self.assertIn("get_dataset_health_report", tools)


class _RecordedLLMClient:
    """Offline client returning one planner JSON response per call (queue)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def complete_json(self, messages, schema):
        self.calls += 1
        if not self._responses:
            raise AssertionError("no recorded response left")
        return self._responses.pop(0)

    def metrics(self):
        return {"status": "success", "usage": {"total_tokens": 10}, "latency_ms": 5, "attempts": 1, "retries": 0}


class M80RecordedLLMReplanningTests(unittest.TestCase):
    def test_recorded_llm_replans_after_step_failure(self):
        reg, adapter = registry(
            ("make_value", "fail_value", "use_value", "recover_value")
        )
        first_plan = {
            "goal": "recorded replan",
            "steps": [
                {"id": "first", "tool": "make_value", "args": {}},
                {"id": "second", "tool": "fail_value", "args": {}, "depends_on": ["first"]},
                {"id": "third", "tool": "use_value", "args": {}, "depends_on": ["second"]},
            ],
            "output": {"type": "buildability_result"},
        }
        second_plan = {
            "goal": "recover with a replacement step",
            "steps": [
                {"id": "recover", "tool": "recover_value", "args": {}, "depends_on": ["first"]},
                {"id": "final", "tool": "use_value", "args": {}, "depends_on": ["recover"]},
            ],
            "output": {"type": "buildability_result"},
        }
        client = _RecordedLLMClient([first_plan, second_plan])
        planner = LLMPlanner(client, reg.names)
        runtime = AgentRuntime(
            planner,
            reg,
            max_retries=0,
            replan_policy=ReplanningPolicy(limit=1),
        )
        result = runtime.run("recorded recover")

        self.assertEqual(client.calls, 2)
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.steps[0].status, "COMPLETED")
        self.assertEqual(result.steps[1].status, "FAILED")
        self.assertEqual([step.tool for step in result.steps[2:]], ["recover_value", "use_value"])
        self.assertEqual(len(result.replan_events), 1)
        self.assertEqual(result.replan_events[0]["failed_step_id"], "second")

    def test_recorded_llm_exhausts_budget_without_replan(self):
        reg, adapter = registry(
            ("make_value", "fail_value", "use_value", "recover_value")
        )
        first_plan = {
            "goal": "recorded no replan",
            "steps": [
                {"id": "first", "tool": "make_value", "args": {}},
                {"id": "second", "tool": "fail_value", "args": {}, "depends_on": ["first"]},
                {"id": "third", "tool": "use_value", "args": {}, "depends_on": ["second"]},
            ],
            "output": {"type": "buildability_result"},
        }
        client = _RecordedLLMClient([first_plan])
        planner = LLMPlanner(client, reg.names)
        runtime = AgentRuntime(
            planner,
            reg,
            max_retries=0,
            replan_policy=ReplanningPolicy(limit=0),
        )
        result = runtime.run("recorded no replan")

        self.assertEqual(client.calls, 1)
        self.assertEqual(result.status.value, "FAILED")
        self.assertEqual(len(result.replan_events), 0)
        self.assertEqual(result.steps[2].status, "BLOCKED")

    def test_replan_events_survive_to_dict_roundtrip(self):
        reg, adapter = registry(
            ("make_value", "fail_value", "use_value", "recover_value")
        )
        runtime = AgentRuntime(
            DowngradePlanner(replacement=replacement_plan()),
            reg,
            max_retries=0,
            replan_policy=ReplanningPolicy(limit=1),
        )
        result = runtime.run("recover me")
        payload = result.to_dict()
        self.assertEqual(len(payload.get("replan_events") or []), 1)
        self.assertEqual(payload["replan_events"][0]["failed_step_id"], "second")
        self.assertNotIn("error", payload["replan_events"][0])
        # Artifact store keeps the bounded events without raw error text.
        from agent.artifact_store import ArtifactStore
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            store = ArtifactStore(root=root)
            ref = store.write_run(payload)
            stored = store.read_run(ref.rsplit("/", 1)[-1].replace(".json", ""))
            self.assertEqual(len(stored.get("replan_events") or []), 1)
            self.assertEqual(stored["replan_events"][0]["failed_step_id"], "second")


if __name__ == "__main__":
    unittest.main()
