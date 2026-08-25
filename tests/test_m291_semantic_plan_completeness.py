import unittest

from agent.application.composite_planning import CompositePlanningApplication
from agent.runtime_core.composite_taskplan import CompositeTaskPlanBridgeError
from agent.runtime_core.plan_completeness import (
    PlanCompletenessError,
    annotate_catalog_capabilities,
    assess_catalog_consistency,
    validate_plan_completeness,
)


class M291PlanCompletenessTests(unittest.TestCase):
    def test_component_fact_clarification_is_not_reported_as_rejection(self):
        class Host:
            def select(self, domain_id, *, source="automatic"):
                del source
                if domain_id != "gis":
                    raise ValueError("unknown domain")
                return domain_id

        class ContextBuilder:
            def build(self, request, **kwargs):
                del request, kwargs
                return {
                    "schema_version": "spatial-agent.composite-request-context.v2",
                    "request_fingerprint": "m291-context",
                    "capability_index": [
                        {
                            "domain_id": "gis",
                            "capability_id": "gis.summary",
                            "available": True,
                            "plan_mode": "task_plan",
                        }
                    ],
                    "clarification": {"state": "not_required"},
                }

        class Planner:
            def plan(self, request, *, context=None):
                del request, context
                component = {
                    "component_id": "summary",
                    "domain_id": "gis",
                    "capability_id": "gis.summary",
                    "request": "补充区域后分析",
                    "depends_on": [],
                    "required": True,
                }
                return {
                    "status": "PLANNED",
                    "planner_source": "replay",
                    "goal": "空间摘要",
                    "message": "",
                    "components": [component],
                    "request": {
                        "schema_version": "spatial-agent.composite-request.v1",
                        "request": "空间摘要",
                        "components": [
                            {
                                "component_id": "summary",
                                "domain_id": "gis",
                                "request": "补充区域后分析",
                                "depends_on": [],
                                "required": True,
                            }
                        ],
                    },
                }

        class Bridge:
            def bridge(self, components, **kwargs):
                del components, kwargs
                raise CompositeTaskPlanBridgeError(
                    "facts are missing", code="taskplan_component_clarification"
                )

        result = CompositePlanningApplication(
            host=Host(),
            projector=object(),
            planner=Planner(),
            composite_runs=object(),
            context_builder=ContextBuilder(),
            taskplan_bridge=Bridge(),
        ).prepare("空间摘要", planner_name="replay", domain_ids=["gis"])
        self.assertEqual(result["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(result["error_code"], "taskplan_component_clarification")

    def test_catalog_receipt_distinguishes_bound_unbound_and_answer_only(self):
        domains = [
            {
                "domain_id": "economic",
                "capabilities": [
                    {
                        "id": "economic_indicator_latest",
                        "tools": ["query"],
                        "result_types": ["metrics"],
                    },
                    {
                        "id": "legacy_report",
                        "tools": ["other"],
                        "result_types": ["legacy_metrics"],
                    },
                    {"id": "conversation", "tools": [], "result_types": ["direct_answer"]},
                ],
                "workflows": [
                    {
                        "id": "economic_indicator_latest",
                        "allowed_tools": ["query"],
                        "result_types": ["metrics"],
                    }
                ],
            }
        ]

        receipt = assess_catalog_consistency({"domains": domains})
        modes = {
            item["capability_id"]: item["plan_mode"]
            for item in receipt["bindings"]
        }
        self.assertEqual(receipt["status"], "degraded")
        self.assertEqual(modes["economic_indicator_latest"], "task_plan")
        self.assertEqual(modes["legacy_report"], "unbound")
        self.assertEqual(modes["conversation"], "answer_only")

        annotated = annotate_catalog_capabilities(domains, receipt)
        legacy = annotated[0]["capabilities"][1]
        self.assertEqual(legacy["plan_mode"], "unbound")
        self.assertEqual(legacy["availability_reason"], "workflow_not_registered")

    def test_plan_completeness_accepts_fully_materialized_components(self):
        components = [
            {
                "component_id": "economic",
                "domain_id": "economic",
                "capability_id": "economic_indicator_latest",
                "request": "查询指标",
            }
        ]
        context = {
            "capability_index": [
                {
                    "domain_id": "economic",
                    "capability_id": "economic_indicator_latest",
                    "plan_mode": "task_plan",
                    "workflow_ids": ["economic_indicator_latest"],
                }
            ]
        }
        receipt = validate_plan_completeness(
            components,
            context=context,
            task_plan_bridge={
                "state": "accepted",
                "materialized_count": 1,
                "components": [{"component_id": "economic", "state": "accepted"}],
            },
        )
        self.assertEqual(receipt["status"], "valid")
        self.assertEqual(receipt["materialized_count"], 1)

    def test_deferred_component_cannot_be_called_planned(self):
        with self.assertRaises(PlanCompletenessError) as error:
            validate_plan_completeness(
                [
                    {
                        "component_id": "economic",
                        "domain_id": "economic",
                        "capability_id": "economic_indicator_latest",
                        "request": "查询指标",
                    }
                ],
                context={
                    "capability_index": [
                        {
                            "domain_id": "economic",
                            "capability_id": "economic_indicator_latest",
                        }
                    ]
                },
                task_plan_bridge={
                    "state": "deferred",
                    "materialized_count": 0,
                    "components": [
                        {
                            "component_id": "economic",
                            "state": "deferred",
                        }
                    ],
                },
            )
        self.assertEqual(error.exception.code, "plan_completeness_failed")

    def test_unbound_capability_is_rejected_before_materialization(self):
        with self.assertRaises(PlanCompletenessError) as error:
            validate_plan_completeness(
                [
                    {
                        "component_id": "legacy",
                        "domain_id": "gis",
                        "capability_id": "legacy_report",
                        "request": "查询旧报告",
                    }
                ],
                context={
                    "capability_index": [
                        {
                            "domain_id": "gis",
                            "capability_id": "legacy_report",
                            "plan_mode": "unbound",
                        }
                    ]
                },
                task_plan_bridge={"state": "accepted", "materialized_count": 1},
            )
        self.assertEqual(error.exception.code, "capability_not_materializable")

    def test_workflow_mismatch_is_not_accepted_by_capability_binding(self):
        with self.assertRaises(PlanCompletenessError) as error:
            validate_plan_completeness(
                [
                    {
                        "component_id": "economic",
                        "domain_id": "economic",
                        "capability_id": "economic_indicator_latest",
                        "request": "查询指标",
                        "workflow": {"template_id": "economic_trend"},
                    }
                ],
                context={
                    "capability_index": [
                        {
                            "domain_id": "economic",
                            "capability_id": "economic_indicator_latest",
                            "plan_mode": "task_plan",
                            "workflow_ids": ["economic_indicator_latest"],
                        }
                    ]
                },
                task_plan_bridge={"state": "accepted", "materialized_count": 1},
            )
        self.assertEqual(error.exception.code, "capability_workflow_mismatch")


if __name__ == "__main__":
    unittest.main()
