"""Compact M319 coverage for policy resolution and Runtime integration."""

from __future__ import annotations

import unittest

from agent.models import PlanStep, RunStatus, TaskPlan
from agent.request_model import RequestFacts
from agent.runtime import AgentRuntime
from agent.runtime_core.execution_policy import (
    ExecutionPolicyError,
    ExecutionPolicyResolver,
)
from agent.tools import ToolRegistry


class _Adapter:
    def invoke(self, name, arguments):
        return {"type": "custom_result", "tool": name, "value": arguments.get("value")}


class _Planner:
    def plan(self, request, workflow=None, context=None):
        del request, workflow, context
        return TaskPlan(
            "执行一个普通工具",
            [PlanStep("step-1", "echo", {"value": "ok"})],
            {"type": "custom_result"},
        )


class _MinimalDomain:
    domain_id = "test-domain"

    def capability_catalog(self, *, environment="unknown"):
        return {
            "schema_version": "spatial-agent.capability-catalog.v1",
            "domain_id": self.domain_id,
            "version": "1.0.0",
            "environment": environment,
            "capabilities": [],
            "workflow_templates": {},
            "dataset_groups": {},
        }

    def discover(self, request, request_facts):
        del request, request_facts
        return {
            "domain_id": self.domain_id,
            "candidate_ids": [],
            "candidate_count": 0,
            "selected_capability_id": None,
        }

    def extract_request_facts(self, request):
        return RequestFacts(
            text=request,
            admin_name=None,
            tasks=(),
            datasets=(),
            constraints={},
            evidence=("answer",),
        )


def _plan(*steps, output="custom_result"):
    return TaskPlan("测试计划", list(steps), {"type": output})


class M319ExecutionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.resolver = ExecutionPolicyResolver(
            known_tools=("alpha", "beta"),
            known_result_profiles=("metrics", "custom_result", "direct_answer"),
            max_actions=4,
            max_turns=6,
        )

    def test_plan_shape_selects_direct_tool_without_workflow(self):
        plan = _plan(PlanStep("one", "alpha", {}))
        policy = self.resolver.resolve_and_validate(plan)
        self.assertEqual(policy["mode"], "direct_tool")
        self.assertEqual(policy["allowed_tools"], ["alpha"])
        self.assertEqual(policy["max_actions"], 1)

    def test_dependent_plan_selects_generated_dag_without_workflow(self):
        plan = _plan(
            PlanStep("one", "alpha", {}),
            PlanStep("two", "beta", {}, ["one"]),
        )
        policy = self.resolver.resolve_and_validate(plan)
        self.assertEqual(policy["mode"], "generated_dag")
        self.assertEqual(policy["max_actions"], 4)

    def test_explicit_workflow_selects_domain_policy_and_confirmation(self):
        plan = _plan(PlanStep("one", "alpha", {}), output="metrics")
        policy = self.resolver.resolve_and_validate(
            plan,
            workflow={
                "template_id": "safe_summary",
                "allowed_tools": ["alpha"],
                "result_types": ["metrics"],
                "max_steps": 2,
            },
            requires_confirmation=True,
        )
        self.assertEqual(policy["mode"], "domain_workflow")
        self.assertTrue(policy["requires_confirmation"])
        self.assertEqual(policy["source"], "explicit_workflow")

    def test_react_mode_keeps_bounded_product_switches(self):
        plan = _plan(PlanStep("one", "alpha", {}))
        policy = self.resolver.resolve_and_validate(
            plan,
            requested_mode="react",
        )
        self.assertEqual(policy["mode"], "react")
        self.assertEqual(policy["max_turns"], 6)
        self.assertTrue(policy["network_enabled"])
        self.assertTrue(policy["tool_proposals_enabled"])

    def test_policy_rejects_tool_result_and_action_budget_drift(self):
        with self.assertRaisesRegex(ExecutionPolicyError, "outside"):
            self.resolver.resolve_and_validate(
                _plan(PlanStep("one", "alpha", {})),
                workflow={"template_id": "safe", "allowed_tools": ["beta"]},
            )
        with self.assertRaises(ExecutionPolicyError):
            self.resolver.resolve_and_validate(
                _plan(PlanStep("one", "alpha", {}), output="unknown_result")
            )
        limited = ExecutionPolicyResolver(
            known_tools=("alpha", "beta"),
            max_actions=1,
        )
        with self.assertRaises(ExecutionPolicyError):
            limited.resolve_and_validate(
                _plan(
                    PlanStep("one", "alpha", {}),
                    PlanStep("two", "beta", {}),
                )
            )

    def test_runtime_accepts_registered_tool_without_workflow(self):
        registry = ToolRegistry(
            {
                "echo": {
                    "input_schema": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "additionalProperties": False,
                    }
                }
            },
            _Adapter(),
        )
        runtime = AgentRuntime(
            _Planner(),
            registry,
            domain_pack=_MinimalDomain(),
        )
        result = runtime.run("执行普通工具")
        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual(result.plan_evidence["execution_policy"]["mode"], "direct_tool")
        self.assertEqual(result.plan_evidence["execution_policy"]["tools"][0]["name"], "echo")


if __name__ == "__main__":
    unittest.main()
