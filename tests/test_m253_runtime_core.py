import unittest

from agent.models import PlanStep, TaskPlan
from agent.runtime import _resolve_result_references
from agent.runtime_core.projection import (
    compact_workflow_templates,
    plan_dag,
    plan_to_dict,
)


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


if __name__ == "__main__":
    unittest.main()
