import json
import unittest

from agent.workflow_templates import (
    WORKFLOW_TEMPLATE_CATALOG,
    WorkflowTemplateError,
    compile_workflow_plan,
    get_workflow_template,
    validate_workflow_plan,
    validate_workflow_template,
    validate_workflow_template_catalog,
    workflow_template_catalog,
)


def _valid_plan(**overrides):
    plan = {
        "template_id": "admin_boundary_query",
        "goal": "查询行政区边界",
        "constraints": {"admin_name": "洪山区"},
        "steps": [
            {
                "id": "schema",
                "tool": "get_dataset_schema",
                "args": {"dataset": "admin_areas"},
                "depends_on": [],
            },
            {
                "id": "query",
                "tool": "range_query",
                "args": {"dataset": "admin_areas", "conditions": [], "limit": 100},
                "depends_on": ["schema"],
            },
        ],
        "output": {"type": "admin_area_result", "summary": True},
    }
    plan.update(overrides)
    return plan


class M68WorkflowTemplateTests(unittest.TestCase):
    def test_catalog_is_json_safe_and_returned_as_an_isolated_copy(self):
        first = workflow_template_catalog()
        json.dumps(first, ensure_ascii=False, allow_nan=False)
        first["admin_boundary_query"]["allowed_tools"].clear()
        second = workflow_template_catalog()
        self.assertEqual(second["admin_boundary_query"]["allowed_tools"], [
            "get_dataset_schema",
            "range_query",
        ])
        self.assertTrue(all("label" in item for item in second.values()))
        self.assertTrue(all(any("\u4e00" <= char <= "\u9fff" for char in item["label"]) for item in second.values()))

    def test_builtin_template_can_validate_and_be_loaded_by_id(self):
        template = get_workflow_template("spatial_overview")
        validated = validate_workflow_template(template)
        self.assertEqual(validated["id"], "spatial_overview")
        self.assertEqual(validated["max_steps"], 8)
        self.assertIn("admin_name", validated["required_constraints"])

    def test_entire_catalog_is_strictly_validated_and_keys_are_bound_to_ids(self):
        validated = validate_workflow_template_catalog(WORKFLOW_TEMPLATE_CATALOG)
        self.assertEqual(set(validated), set(WORKFLOW_TEMPLATE_CATALOG))
        catalog = workflow_template_catalog()
        catalog["wrong_key"] = catalog.pop("raster_metadata")
        with self.assertRaisesRegex(WorkflowTemplateError, "does not match"):
            validate_workflow_template_catalog(catalog)

    def test_unknown_template_id_is_rejected(self):
        with self.assertRaisesRegex(WorkflowTemplateError, "unknown workflow template"):
            get_workflow_template("does_not_exist")

    def test_unknown_tool_in_template_is_rejected(self):
        template = get_workflow_template("admin_boundary_query")
        template["allowed_tools"] = ["not_a_tool"]
        with self.assertRaisesRegex(WorkflowTemplateError, "unknown tool"):
            validate_workflow_template(template)

    def test_unknown_result_type_in_template_is_rejected(self):
        template = get_workflow_template("admin_boundary_query")
        template["result_types"] = ["not_a_result"]
        with self.assertRaisesRegex(WorkflowTemplateError, "unknown result type"):
            validate_workflow_template(template)

    def test_template_shape_and_duplicate_declarations_are_strict(self):
        template = get_workflow_template("admin_boundary_query")
        template["extra"] = True
        with self.assertRaisesRegex(WorkflowTemplateError, "unknown fields"):
            validate_workflow_template(template)

        template = get_workflow_template("admin_boundary_query")
        template["required_constraints"] = ["admin_name", "admin_name"]
        with self.assertRaisesRegex(WorkflowTemplateError, "duplicate"):
            validate_workflow_template(template)

    def test_valid_plan_is_returned_as_a_copy_with_normalized_dependencies(self):
        plan = _valid_plan()
        validated = validate_workflow_plan("admin_boundary_query", plan)
        self.assertEqual(validated["template_id"], "admin_boundary_query")
        self.assertEqual(validated["steps"][1]["depends_on"], ["schema"])
        validated["steps"][0]["args"]["dataset"] = "changed"
        self.assertEqual(plan["steps"][0]["args"]["dataset"], "admin_areas")

    def test_required_constraints_must_be_present_and_non_empty(self):
        for constraints in ({}, {"admin_name": ""}, {"admin_name": None}):
            with self.subTest(constraints=constraints):
                with self.assertRaisesRegex(WorkflowTemplateError, "required constraints"):
                    validate_workflow_plan(
                        "admin_boundary_query", _valid_plan(constraints=constraints)
                    )

    def test_plan_rejects_tool_outside_template_allowlist(self):
        steps = _valid_plan()["steps"]
        steps[1] = {**steps[1], "tool": "get_raster_metadata"}
        with self.assertRaisesRegex(WorkflowTemplateError, "not allowed"):
            validate_workflow_plan("admin_boundary_query", _valid_plan(steps=steps))

    def test_plan_rejects_unknown_tool_distinctly(self):
        steps = _valid_plan()["steps"]
        steps[1] = {**steps[1], "tool": "not_a_tool"}
        with self.assertRaisesRegex(WorkflowTemplateError, "unknown tool"):
            validate_workflow_plan("admin_boundary_query", _valid_plan(steps=steps))

    def test_plan_rejects_unknown_result_type(self):
        with self.assertRaisesRegex(WorkflowTemplateError, "unknown result type"):
            validate_workflow_plan(
                "admin_boundary_query",
                _valid_plan(output={"type": "not_a_result"}),
            )

    def test_plan_rejects_duplicate_step_ids(self):
        steps = _valid_plan()["steps"]
        steps[1] = {**steps[1], "id": "schema"}
        with self.assertRaisesRegex(WorkflowTemplateError, "duplicate step id"):
            validate_workflow_plan("admin_boundary_query", _valid_plan(steps=steps))

    def test_plan_rejects_dependency_cycle(self):
        steps = [
            {"id": "a", "tool": "get_dataset_schema", "args": {}, "depends_on": ["b"]},
            {"id": "b", "tool": "range_query", "args": {}, "depends_on": ["a"]},
        ]
        with self.assertRaisesRegex(WorkflowTemplateError, "cycle"):
            validate_workflow_plan(
                "admin_boundary_query", _valid_plan(steps=steps)
            )

    def test_plan_rejects_unknown_and_self_dependencies(self):
        steps = _valid_plan()["steps"]
        steps[1] = {**steps[1], "depends_on": ["missing"]}
        with self.assertRaisesRegex(WorkflowTemplateError, "unknown step"):
            validate_workflow_plan("admin_boundary_query", _valid_plan(steps=steps))

        steps[1] = {**steps[1], "depends_on": ["query"]}
        with self.assertRaisesRegex(WorkflowTemplateError, "itself"):
            validate_workflow_plan("admin_boundary_query", _valid_plan(steps=steps))

    def test_plan_rejects_more_steps_than_template_allows(self):
        steps = _valid_plan()["steps"] + [
            {"id": "third", "tool": "range_query", "args": {}, "depends_on": []}
        ]
        with self.assertRaisesRegex(WorkflowTemplateError, "max_steps"):
            validate_workflow_plan("admin_boundary_query", _valid_plan(steps=steps))

    def test_plan_rejects_malformed_json_and_unknown_fields(self):
        with self.assertRaisesRegex(WorkflowTemplateError, "JSON-safe"):
            validate_workflow_plan(
                "admin_boundary_query",
                _valid_plan(constraints={"admin_name": {"bad"}}),
            )
        plan = _valid_plan()
        plan["unexpected"] = True
        with self.assertRaisesRegex(WorkflowTemplateError, "unknown fields"):
            validate_workflow_plan("admin_boundary_query", plan)

    def test_custom_known_sets_support_explicit_extension_catalogs(self):
        template = {
            "id": "custom",
            "label": "自定义流程",
            "allowed_tools": ["custom_tool"],
            "result_types": ["custom_result"],
            "max_steps": 1,
            "required_constraints": [],
        }
        plan = {
            "steps": [{"id": "one", "tool": "custom_tool", "args": {}}],
            "output": {"type": "custom_result"},
        }
        self.assertEqual(
            validate_workflow_plan(
                template,
                plan,
                known_tools=["custom_tool"],
                known_result_types=["custom_result"],
            )["output"]["type"],
            "custom_result",
        )

    def test_template_compiler_binds_constraints_and_result_references(self):
        plan = compile_workflow_plan("spatial_overview", {"admin_name": "洪山区"})

        self.assertEqual(plan["template_id"], "spatial_overview")
        self.assertEqual(plan["constraints"]["admin_name"], "洪山区")
        self.assertEqual(len(plan["steps"]), 8)
        self.assertEqual(
            plan["steps"][2]["args"]["conditions"][0]["value"],
            "洪山区",
        )
        self.assertEqual(
            plan["steps"][3]["args"]["admin_name"],
            {"$from": "filter-admin", "path": "first_name"},
        )
        self.assertEqual(plan["output"]["type"], "spatial_overview_result")

    def test_template_compiler_rejects_bad_blueprints_before_runtime(self):
        template = get_workflow_template("admin_boundary_query")
        template["step_blueprint"][1]["tool"] = "get_raster_metadata"

        with self.assertRaisesRegex(WorkflowTemplateError, "outside allowed_tools"):
            validate_workflow_template(template)


if __name__ == "__main__":
    unittest.main()
