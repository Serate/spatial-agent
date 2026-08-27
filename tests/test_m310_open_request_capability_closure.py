"""M310-A: request-fact requirements keep one bounded cardinality contract."""

from __future__ import annotations

import unittest

from agent.capability_catalog import project_clarification_requirements
from agent.application.composite_planning import CompositePlanningApplication
from agent.composite_planner import ReplayCompositePlanner
from agent.data_readiness import project_data_readiness
from agent.request_requirements import (
    missing_requirement_fields,
    normalize_request_requirements,
    requirement_satisfied,
)
from agent.runtime_core.component_fact_handoff import (
    build_component_fact_handoff,
    normalize_component_fact_handoff,
)
from agent.runtime_core.composite_taskplan import (
    CompositeTaskPlanBridge,
    CompositeTaskPlanBridgeError,
)
from agent.runtime_core.planner_envelope import build_planner_envelope


REQUIREMENTS = {
    "datasets": ["dem", "land_use"],
    "clarification_fields": [
        {
            "id": "dataset",
            "label": "数据集",
            "kind": "dataset",
            "values": ["dem", "land_use"],
            "mode": "one",
        }
    ],
}


def _component_context(datasets):
    return {
        "schema_version": "spatial-agent.composite-request-context.v2",
        "request_fingerprint": "m310-facts",
        "domain_ids": ["demo"],
        "capability_index": [
            {
                "domain_id": "demo",
                "capability_id": "demo.raster",
                "request_requirements": REQUIREMENTS,
            }
        ],
        "domain_contexts": [
            {
                "domain_id": "demo",
                "facts": {
                    "schema_version": "spatial-agent.request-facts.v1",
                    "datasets": list(datasets),
                    "entities": {},
                    "constraints": {},
                },
            }
        ],
    }


class _WorkflowService:
    def __init__(self, workflow, *, preview_response=None, preview_error=None):
        self.workflow = workflow
        self.preview_response = preview_response
        self.preview_error = preview_error
        self.preview_calls = 0

    def resolve_capability_selection(self, capability_id, **kwargs):
        del capability_id, kwargs
        return self.workflow

    def preview(self, request, **kwargs):
        del request, kwargs
        self.preview_calls += 1
        if self.preview_error is not None:
            raise self.preview_error
        if self.preview_response is not None:
            return self.preview_response
        return {
            "status": "PLANNED",
            "plan": {
                "goal": "测试工作流",
                "steps": [
                    {
                        "id": "step-1",
                        "tool": "demo.query",
                        "args": {},
                        "depends_on": [],
                    }
                ],
                "output": {"type": "demo.result"},
            },
        }


class _WorkflowHost:
    def __init__(self, service):
        self.service_instance = service

    def select(self, domain_id, *, source="explicit"):
        del source
        if domain_id != "demo":
            raise ValueError("unknown domain")
        return domain_id

    def service(self, selection):
        if selection != "demo":
            raise ValueError("unknown domain")
        return self.service_instance


class _ContextBuilder:
    def __init__(self, context):
        self.context = context

    def build(self, request, **kwargs):
        del request, kwargs
        return self.context


class _AcceptedBridgeWithoutPlan:
    def bridge(self, components, **kwargs):
        del kwargs
        return {
            "state": "accepted",
            "component_count": len(components),
            "materialized_count": len(components),
            "deferred_count": 0,
            "components": [
                {
                    "component_id": item["component_id"],
                    "domain_id": item["domain_id"],
                    "state": "accepted",
                    "policy": {
                        "allowed_tools": ["demo.query"],
                        "result_types": ["demo.result"],
                        "max_steps": 1,
                    },
                }
                for item in components
            ],
        }


def _workflow_context():
    return {
        "schema_version": "spatial-agent.composite-request-context.v2",
        "request_fingerprint": "m310-workflow",
        "workflow_index": [
            {
                "domain_id": "demo",
                "workflow_id": "demo.summary",
                "allowed_tools": ["demo.query"],
                "result_types": ["demo.result"],
            }
        ],
        "capability_index": [
            {
                "domain_id": "demo",
                "capability_id": "demo.summary",
                "tools": ["demo.query"],
                "result_types": ["demo.result"],
                "workflow_ids": ["demo.summary"],
                "plan_mode": "task_plan",
                "available": True,
                "execution_ready": True,
                "request_requirements": {"clarification_fields": []},
            }
        ],
        "domain_contexts": [
            {
                "domain_id": "demo",
                "facts": {
                    "schema_version": "spatial-agent.request-facts.v1",
                    "entities": {},
                    "datasets": [],
                    "constraints": {},
                },
            }
        ],
    }


def _workflow_component():
    return {
        "component_id": "summary",
        "domain_id": "demo",
        "capability_id": "demo.summary",
        "request": "生成摘要",
        "depends_on": [],
        "required": True,
    }


def _planning_payload():
    return {
        "outcome": "success",
        "goal": "生成摘要",
        "message": "",
        "components": [_workflow_component()],
    }


class M310RequestFactRequirementTests(unittest.TestCase):
    def test_data_readiness_preserves_spatial_temporal_and_source_facts_safely(self):
        readiness = project_data_readiness(
            {
                "status": "partial",
                "coverage": {"bbox": [114.2, 30.4, 114.6, 30.7]},
                "time_range": {"start": "2020", "end": "2025"},
                "crs": "EPSG:4326",
                "resolution": "30m",
                "alignment": {
                    "status": "aligned",
                    "method": "grid_check",
                    "source_path": "must-not-leak",
                },
                "source_id": "wuhan-dem",
                "source_url": "https://example.invalid/dem",
                "private_file_path": "must-not-leak",
            }
        )

        self.assertEqual(readiness["schema_version"], "spatial-agent.data-readiness.v1")
        self.assertEqual(readiness["status"], "partial")
        self.assertEqual(readiness["crs"], "EPSG:4326")
        self.assertEqual(readiness["alignment"]["status"], "aligned")
        self.assertNotIn("source_path", readiness["alignment"])
        self.assertNotIn("private_file_path", readiness)

    def test_planner_selection_keeps_readiness_for_selected_capability(self):
        readiness = {
            "status": "partial",
            "coverage": {"bbox": [114.2, 30.4, 114.6, 30.7]},
            "time_range": {"start": "2020", "end": "2025"},
            "crs": "EPSG:4326",
            "alignment": {"status": "aligned"},
        }
        context = _workflow_context()
        context["data_readiness"] = {"status": "partial", "domains": {"demo": readiness}}
        context["domain_contexts"][0]["data_readiness"] = readiness
        envelope = build_planner_envelope(context, projection_stage="selection")

        projected = envelope["execution_contract"]["data_readiness"]["domains"]["demo"]
        self.assertEqual(projected["status"], "partial")
        self.assertEqual(projected["crs"], "EPSG:4326")
        self.assertEqual(projected["alignment"]["status"], "aligned")

    def test_one_requires_exactly_one_declared_choice(self):
        normalized = normalize_request_requirements(REQUIREMENTS)
        field = normalized["clarification_fields"][0]

        self.assertEqual(field["mode"], "one")
        self.assertFalse(requirement_satisfied(field, normalized, {"datasets": []}))
        self.assertTrue(
            requirement_satisfied(field, normalized, {"datasets": ["dem"]})
        )
        self.assertFalse(
            requirement_satisfied(field, normalized, {"datasets": ["dem", "land_use"]})
        )

    def test_catalog_clarification_keeps_mode_and_choices(self):
        projection = project_clarification_requirements(
            ["demo.raster"],
            {"datasets": ["dem", "land_use"]},
            capability_definitions=[
                {
                    "id": "demo.raster",
                    "request_requirements": REQUIREMENTS,
                }
            ],
        )

        self.assertEqual(projection["missing"], ["数据集"])
        field = projection["missing_fields"][0]
        self.assertEqual(field["mode"], "one")
        self.assertEqual(field["values"], ["dem", "land_use"])

    def test_component_handoff_uses_same_one_semantics_and_preserves_metadata(self):
        component = {
            "component_id": "raster",
            "domain_id": "demo",
            "capability_id": "demo.raster",
        }
        ambiguous = build_component_fact_handoff(
            component, context=_component_context(["dem", "land_use"])
        )
        self.assertEqual(ambiguous["state"], "required")
        self.assertEqual(ambiguous["missing_fields"][0]["mode"], "one")
        self.assertEqual(
            ambiguous["missing_fields"][0]["values"], ["dem", "land_use"]
        )

        ready = build_component_fact_handoff(
            component, context=_component_context(["dem"])
        )
        self.assertEqual(ready["state"], "ready")
        restored = normalize_component_fact_handoff(ambiguous)
        self.assertEqual(restored["missing_fields"][0]["mode"], "one")

    def test_workflow_constraints_can_complete_a_declared_constraint(self):
        requirements = {
            "constraints": ["limit", "period"],
            "clarification_fields": [
                {
                    "id": "analysis_constraints",
                    "label": "分析条件",
                    "kind": "constraint",
                    "keys": ["limit", "period"],
                    "mode": "all",
                }
            ],
        }
        missing = missing_requirement_fields(
            requirements,
            {"constraints": {"limit": 10}},
            workflow_constraints={"period": "2025"},
        )
        self.assertEqual(missing, [])

    def test_planner_envelope_does_not_drop_requirement_cardinality(self):
        envelope = build_planner_envelope(
            {
                "schema_version": "spatial-agent.composite-request-context.v2",
                "planner": "openai",
                "backend": "local",
                "request_fingerprint": "m310-envelope",
                "request_summary": "选择一个栅格数据集",
                "capability_index": [
                    {
                        "domain_id": "demo",
                        "capability_id": "demo.raster",
                        "selection_key": "demo::demo.raster",
                        "label": "栅格分析",
                        "available": True,
                        "request_requirements": REQUIREMENTS,
                    }
                ],
            },
            projection_stage="selection",
        )
        field = envelope["capability_index"][0]["request_requirements"][
            "clarification_fields"
        ][0]
        self.assertEqual(field["mode"], "one")
        self.assertEqual(field["values"], ["dem", "land_use"])

    def test_selected_capability_resolves_its_domain_workflow_before_preview(self):
        service = _WorkflowService({"template_id": "demo.summary"})
        bridge = CompositeTaskPlanBridge(host=_WorkflowHost(service))
        result = bridge.bridge(
            [_workflow_component()],
            context=_workflow_context(),
            planner="llm",
            backend="local",
        )
        self.assertEqual(result["state"], "accepted")
        self.assertEqual(result["components"][0]["source"], "domain_preview")
        self.assertEqual(service.preview_calls, 1)

    def test_resolver_workflow_mismatch_fails_before_preview(self):
        service = _WorkflowService({"template_id": "demo.other"})
        bridge = CompositeTaskPlanBridge(host=_WorkflowHost(service))
        with self.assertRaises(CompositeTaskPlanBridgeError) as error:
            bridge.bridge(
                [_workflow_component()],
                context=_workflow_context(),
                planner="llm",
                backend="local",
            )
        self.assertEqual(error.exception.code, "capability_workflow_mismatch")
        self.assertEqual(service.preview_calls, 0)

    def test_missing_domain_workflow_is_not_reported_as_preview_failure(self):
        service = _WorkflowService(None)
        bridge = CompositeTaskPlanBridge(host=_WorkflowHost(service))
        with self.assertRaises(CompositeTaskPlanBridgeError) as error:
            bridge.bridge(
                [_workflow_component()],
                context=_workflow_context(),
                planner="llm",
                backend="local",
            )
        self.assertEqual(error.exception.code, "capability_workflow_unresolved")
        self.assertEqual(service.preview_calls, 0)

    def test_domain_resolver_failure_cannot_fall_back_to_context_workflow(self):
        service = _WorkflowService(None)
        context = _workflow_context()
        context["domain_contexts"][0]["workflow"] = {
            "selected_capability_id": "demo.summary",
            "workflow_template_id": "demo.summary",
        }
        bridge = CompositeTaskPlanBridge(host=_WorkflowHost(service))

        with self.assertRaises(CompositeTaskPlanBridgeError) as error:
            bridge.bridge(
                [_workflow_component()],
                context=context,
                planner="llm",
                backend="local",
            )

        self.assertEqual(error.exception.code, "capability_workflow_unresolved")
        self.assertEqual(service.preview_calls, 0)

    def test_application_keeps_unavailable_and_unbound_capabilities_distinct(self):
        for field, value, expected_status, expected_code in (
            ("available", False, "NEEDS_CLARIFICATION", "capability_unavailable"),
            ("plan_mode", "unbound", "REJECTED", "capability_not_materializable"),
        ):
            with self.subTest(field=field):
                context = _workflow_context()
                context["capability_index"][0][field] = value
                application = CompositePlanningApplication(
                    host=_WorkflowHost(_WorkflowService({"template_id": "demo.summary"})),
                    projector=object(),
                    planner=ReplayCompositePlanner(_planning_payload()),
                    composite_runs=object(),
                    context_builder=_ContextBuilder(context),
                )

                result = application.prepare(
                    "生成摘要",
                    planner_name="replay",
                    backend="memory",
                    domain_ids=["demo"],
                )

                self.assertEqual(result["status"], expected_status)
                self.assertEqual(result.get("error_code"), expected_code)

    def test_application_projects_preview_failures_without_creating_a_run(self):
        for service_kwargs, expected_state, expected_code in (
            (
                {"preview_response": []},
                "preview_invalid",
                "taskplan_component_preview_invalid",
            ),
            (
                {"preview_error": RuntimeError("private preview detail")},
                "preview_failed",
                "taskplan_component_preview_failed",
            ),
        ):
            with self.subTest(expected_state=expected_state):
                service = _WorkflowService(
                    {"template_id": "demo.summary"}, **service_kwargs
                )
                application = CompositePlanningApplication(
                    host=_WorkflowHost(service),
                    projector=object(),
                    planner=ReplayCompositePlanner(_planning_payload()),
                    composite_runs=object(),
                    context_builder=_ContextBuilder(_workflow_context()),
                )

                result = application.submit(
                    "生成摘要",
                    planner_name="replay",
                    backend="memory",
                    domain_ids=["demo"],
                    asynchronous=False,
                )

                self.assertEqual(result["status"], "REJECTED")
                self.assertEqual(result["planning_failure"]["state"], expected_state)
                self.assertEqual(result["planning_failure"]["code"], expected_code)
                self.assertFalse(result["planning_failure"]["execution_run_created"])
                self.assertEqual(result["failure"]["phase"], "planning")

    def test_application_projects_binding_failure_after_taskplan_gate(self):
        application = CompositePlanningApplication(
            host=_WorkflowHost(_WorkflowService({"template_id": "demo.summary"})),
            projector=object(),
            planner=ReplayCompositePlanner(_planning_payload()),
            composite_runs=object(),
            context_builder=_ContextBuilder(_workflow_context()),
            taskplan_bridge=_AcceptedBridgeWithoutPlan(),
        )

        result = application.submit(
            "生成摘要",
            planner_name="replay",
            backend="memory",
            domain_ids=["demo"],
            asynchronous=False,
        )

        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["planning_failure"]["state"], "binding_failed")
        self.assertEqual(
            result["planning_failure"]["code"], "execution_binding_plan_missing"
        )
        self.assertFalse(result["planning_failure"]["execution_run_created"])


if __name__ == "__main__":
    unittest.main()
