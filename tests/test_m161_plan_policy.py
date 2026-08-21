"""M161: plan-policy evidence is Domain-owned and cross-entry stable."""

import copy
import unittest

from agent.models import PlanStep, TaskPlan
from agent.errors import ClarificationNeeded
from agent.runtime import AgentRuntime
from agent.tools import DemoSpatialAdapter, ToolRegistry
from agent.plan_policy import (
    PLAN_POLICY_SCHEMA_VERSION,
    build_plan_policy_evidence,
    normalize_plan_policy_evidence,
)
from agent.runtime_factory import build_runtime
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.text.domain import TEXT_DOMAIN_PACK
from evaluation.contract_harness import normalize_result
from result_contract import build_result_contract


def _admin_plan() -> TaskPlan:
    return TaskPlan(
        goal="query boundary",
        steps=[
            PlanStep("schema-admin", "get_dataset_schema", {"dataset": "admin_areas"}),
            PlanStep(
                "filter-admin",
                "range_query",
                {"dataset": "admin_areas", "conditions": [], "limit": 100},
                ["schema-admin"],
            ),
        ],
        output={"type": "admin_area_result", "summary": True},
    )


class M161PlanPolicyTests(unittest.TestCase):
    def test_gis_policy_records_explicit_selection_and_limits(self):
        plan = _admin_plan()
        policy = GIS_DOMAIN_PACK.plan_policy(
            plan,
            workflow={
                "template_id": "admin_boundary_query",
                "template_version": "1.0.0",
            },
        )
        evidence = build_plan_policy_evidence(
            plan,
            domain_policy=policy,
            workflow={
                "template_id": "admin_boundary_query",
                "template_version": "1.0.0",
            },
            domain_id="gis",
        )
        self.assertEqual(evidence["schema_version"], PLAN_POLICY_SCHEMA_VERSION)
        self.assertTrue(evidence["available"])
        self.assertTrue(evidence["accepted"])
        self.assertEqual(evidence["source"], "explicit_workflow")
        self.assertEqual(evidence["policy_id"], "gis.workflow.admin_boundary_query")
        self.assertEqual(evidence["max_steps"], 2)
        self.assertIn("range_query", evidence["allowed_tools"])

    def test_text_policy_does_not_inherit_gis_workflow_rules(self):
        plan = TaskPlan(
            goal="summarize",
            steps=[PlanStep("summary", "summarize_text", {"text": "hello"})],
            output={"type": "text_summary_result"},
        )
        policy = TEXT_DOMAIN_PACK.plan_policy(plan)
        evidence = build_plan_policy_evidence(
            plan,
            domain_policy=policy,
            domain_id="text",
        )
        self.assertFalse(evidence["available"])
        self.assertTrue(evidence["accepted"])
        self.assertEqual(evidence["source"], "none")
        self.assertEqual(evidence["allowed_tools"], [])
        self.assertNotIn("get_raster_metadata", evidence["allowed_tools"])

    def test_repair_lineage_is_bounded_and_normalized(self):
        evidence = build_plan_policy_evidence(
            _admin_plan(),
            domain_policy=GIS_DOMAIN_PACK.plan_policy(_admin_plan()),
            domain_id="gis",
            state="accepted",
            reason_code="execution_replan_accepted",
            repair_lineage=[
                {
                    "phase": "execution",
                    "failed_step_id": "filter-admin",
                    "failed_tool": "range_query",
                    "failure_category": "tool_gate",
                    "replanned_step_ids": ["fallback"],
                    "occurred_at": 9999999999,
                    "error": "must not be persisted",
                }
            ],
        )
        self.assertEqual(evidence["repair_lineage"][0]["phase"], "execution")
        self.assertNotIn("error", evidence["repair_lineage"][0])
        restored = normalize_plan_policy_evidence(copy.deepcopy(evidence))
        self.assertEqual(restored, evidence)

    def test_runtime_result_and_harness_expose_same_policy(self):
        runtime = build_runtime("rule", "memory", domain_pack=TEXT_DOMAIN_PACK)
        result = runtime.run("概括这段文本")
        payload = result.to_dict()
        payload["answer"] = result.answer
        payload["result_type"] = "text_summary_result"
        payload["result"] = build_result_contract(payload, registry=runtime.result_registry())
        planning = payload["result"]["planning"]
        self.assertEqual(planning["plan_policy"]["schema_version"], PLAN_POLICY_SCHEMA_VERSION)
        self.assertEqual(planning["plan_policy"]["domain_id"], "text")
        harness = normalize_result(payload).as_dict()
        self.assertEqual(harness["plan_policy"], planning["plan_policy"])

    def test_runtime_preserves_rejection_policy_after_invalid_domain_plan(self):
        class InvalidPlanner:
            def plan(self, request, workflow=None, context=None):
                del request, workflow, context
                return TaskPlan(
                    goal="invalid boundary plan",
                    steps=[
                        PlanStep("schema", "get_dataset_schema", {"dataset": "admin_areas"}),
                        PlanStep("extra", "get_raster_metadata", {"dataset": "dem"}),
                    ],
                    output={"type": "admin_area_result"},
                )

        registry = ToolRegistry.from_json(
            "tools/schema/tool-definitions.json", DemoSpatialAdapter()
        )
        result = AgentRuntime(
            InvalidPlanner(),
            registry,
            domain_pack=GIS_DOMAIN_PACK,
        ).run("查询行政区边界")
        self.assertEqual(result.status.value, "FAILED")
        self.assertEqual(result.plan_evidence["plan_policy"]["state"], "rejected")
        self.assertFalse(result.plan_evidence["plan_policy"]["accepted"])
        self.assertEqual(
            result.plan_evidence["plan_policy"]["reason_code"],
            "plan_validation_rejected",
        )

    def test_runtime_preserves_clarification_policy_without_a_plan(self):
        class ClarifyingPlanner:
            def plan(self, request, workflow=None, context=None):
                del request, workflow, context
                raise ClarificationNeeded("需要补充区域")

        registry = ToolRegistry.from_json(
            "tools/schema/tool-definitions.json", DemoSpatialAdapter()
        )
        result = AgentRuntime(
            ClarifyingPlanner(),
            registry,
            domain_pack=GIS_DOMAIN_PACK,
        ).run("进行空间分析")
        self.assertEqual(result.status.value, "NEEDS_CLARIFICATION")
        self.assertEqual(result.plan_evidence["plan_policy"]["state"], "clarification")
        self.assertEqual(
            result.plan_evidence["plan_policy"]["reason_code"],
            "clarification_required",
        )


if __name__ == "__main__":
    unittest.main()
