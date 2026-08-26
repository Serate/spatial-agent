"""M303-B: structured planner output becomes one canonical Composite DAG."""

from __future__ import annotations

import unittest
import tempfile
import threading
import time
from pathlib import Path

from agent.application.composite_planning import CompositePlanningApplication
from agent.application.composite_runs import CompositeRunApplication
from agent.composite_contract import build_composite_result_contract
from agent.composite_planner import (
    CompositePlannerError,
    LLMCompositePlanner,
    ReplayCompositePlanner,
    RuleCompositePlanner,
)


CONTEXT = {
    "schema_version": "spatial-agent.composite-request-context.v2",
    "request_fingerprint": "m303-context",
    "capability_index": [
        {
            "domain_id": "gis",
            "capability_id": "gis.summary",
            "available": True,
            "plan_mode": "workflow",
            "execution_ready": True,
            "output_profiles": [{"kinds": ["vector"]}],
        },
        {
            "domain_id": "economic",
            "capability_id": "economic.summary",
            "available": True,
            "plan_mode": "workflow",
            "execution_ready": True,
            "output_profiles": [{"kinds": ["table"]}],
        },
    ],
}


def _two_component_payload() -> dict[str, object]:
    return {
        "outcome": "success",
        "goal": "组合分析",
        "message": "",
        "components": [
            {
                "component_id": "Source",
                "domain_id": "GIS",
                "capability_id": "gis.summary",
                "request": "生成空间摘要",
                "depends_on": [],
                "required": True,
            },
            {
                "component_id": "Target",
                "domain_id": "economic",
                "capability_id": "economic.summary",
                "request": "结合空间摘要分析指标",
                "depends_on": ["SOURCE"],
                "required": True,
                "inputs": [
                    {
                        "name": "空间摘要",
                        "source": {"component_id": "SOURCE", "path": "result.items"},
                        "accepted_kinds": ["vector"],
                        "required": True,
                    }
                ],
            },
        ],
    }


class M303CanonicalPlanAdapterTests(unittest.TestCase):
    def test_identity_and_references_are_rebuilt_from_canonical_request(self):
        result = ReplayCompositePlanner(_two_component_payload()).plan(
            "分析空间与指标", context=CONTEXT
        )

        self.assertEqual(result["status"], "PLANNED")
        request_components = result["request"]["components"]
        projected_components = result["components"]
        self.assertEqual(
            [item["component_id"] for item in request_components],
            ["source", "target"],
        )
        self.assertEqual(projected_components[1]["depends_on"], ["source"])
        self.assertEqual(
            projected_components[1]["inputs"][0]["source"]["component_id"],
            "source",
        )
        self.assertEqual(projected_components[0]["domain_id"], "gis")
        self.assertEqual(projected_components[0]["capability_id"], "gis.summary")
        self.assertNotIn("capability_id", request_components[0])

    def test_invalid_scalar_shape_fails_closed_in_planner_adapter(self):
        payload = _two_component_payload()
        payload["components"][0]["required"] = "false"  # type: ignore[index]

        with self.assertRaises(CompositePlannerError) as error:
            ReplayCompositePlanner(payload).plan("分析空间与指标", context=CONTEXT)

        self.assertEqual(error.exception.code, "plan_component_field_invalid")

    def test_cycle_is_reported_as_canonical_planner_error(self):
        payload = _two_component_payload()
        payload["components"][0]["depends_on"] = ["TARGET"]  # type: ignore[index]

        with self.assertRaises(CompositePlannerError) as error:
            ReplayCompositePlanner(payload).plan("分析空间与指标", context=CONTEXT)

        self.assertEqual(error.exception.code, "composite_dependency_cycle")

    def test_empty_success_plan_is_rejected_before_execution(self):
        payload = {
            "outcome": "success",
            "goal": "组合分析",
            "message": "",
            "components": [],
        }

        with self.assertRaises(CompositePlannerError) as error:
            ReplayCompositePlanner(payload).plan("分析空间与指标", context=CONTEXT)

        self.assertEqual(error.exception.code, "plan_components_required")

    def test_llm_cannot_smuggle_workflow_into_capability_selection(self):
        payload = _two_component_payload()
        payload["components"][0]["workflow"] = {"task_plan": {}}  # type: ignore[index]

        class _Client:
            def complete_json(self, messages, schema):
                del messages, schema
                return payload

        with self.assertRaises(CompositePlannerError) as error:
            LLMCompositePlanner(_Client()).plan("分析空间与指标", context=CONTEXT)

        self.assertEqual(error.exception.code, "plan_component_workflow_forbidden")


EXECUTION_CONTEXT = {
    "schema_version": "spatial-agent.composite-request-context.v2",
    "request_fingerprint": "m303-execution-context",
    "clarification": {"state": "not_required"},
    "capability_index": [
        {
            "domain_id": "gis",
            "capability_id": "gis.summary",
            "available": True,
            "tools": ["tool-a"],
            "result_types": ["summary_result"],
            "execution_ready": True,
        },
        {
            "domain_id": "economic",
            "capability_id": "economic.summary",
            "available": True,
            "tools": ["tool-a"],
            "result_types": ["summary_result"],
            "execution_ready": True,
        },
    ],
}


class _ExecutionService:
    def preview(self, request, **kwargs):
        del request, kwargs
        return {
            "status": "PLANNED",
            "plan": {
                "goal": "执行组件",
                "steps": [
                    {
                        "id": "step",
                        "tool": "tool-a",
                        "args": {},
                        "depends_on": [],
                    }
                ],
                "output": {"type": "summary_result"},
                "assumptions": [],
            },
        }


class _ExecutionHost:
    def select(self, domain_id, *, source="automatic"):
        del source
        if domain_id not in {"gis", "economic"}:
            raise ValueError("unknown domain")
        return domain_id

    def service(self, selection):
        if selection not in {"gis", "economic"}:
            raise ValueError("unknown service")
        return _ExecutionService()


class _ExecutionContext:
    def build(self, request, *, planner="rule", backend="memory", domain_ids=None):
        del request, planner, backend, domain_ids
        return dict(EXECUTION_CONTEXT)


class M303ExecutionClosureTests(unittest.TestCase):
    def test_rule_replay_and_llm_share_the_same_canonical_identity(self):
        class _Client:
            def complete_json(self, messages, schema):
                del messages, schema
                return _two_component_payload()

        results = [
            ReplayCompositePlanner(_two_component_payload()).plan(
                "分析空间与指标", context=CONTEXT
            ),
            RuleCompositePlanner(lambda request, context: _two_component_payload()).plan(
                "分析空间与指标", context=CONTEXT
            ),
            LLMCompositePlanner(_Client()).plan("分析空间与指标", context=CONTEXT),
        ]

        self.assertEqual({item["status"] for item in results}, {"PLANNED"})
        self.assertEqual(
            {item["request"]["fingerprint"] for item in results},
            {results[0]["request"]["fingerprint"]},
        )
        self.assertEqual(
            [item["component_id"] for item in results[2]["components"]],
            ["source", "target"],
        )

    def test_planned_components_cross_taskplan_and_binding_once(self):
        result = CompositePlanningApplication(
            host=_ExecutionHost(),
            projector=object(),
            planner=ReplayCompositePlanner(_two_component_payload()),
            composite_runs=object(),
            context_builder=_ExecutionContext(),
        ).prepare("分析空间与指标", planner_name="replay", domain_ids=["gis", "economic"])

        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(result["task_plan_bridge"]["state"], "accepted")
        self.assertEqual(result["execution_binding"]["state"], "validated")
        self.assertEqual(result["execution_binding"]["component_ids"], ["source", "target"])
        self.assertEqual(
            result["planner_evidence"]["execution_projection"]["execution_identity"]["component_ids"],
            ["source", "target"],
        )

    def test_unknown_capability_is_rejected_before_taskplan_bridge(self):
        payload = _two_component_payload()
        payload["components"][0]["capability_id"] = "gis.unknown"  # type: ignore[index]

        with self.assertRaises(CompositePlannerError) as error:
            ReplayCompositePlanner(payload).plan("分析空间与指标", context=CONTEXT)

        self.assertEqual(error.exception.code, "capability_not_registered")


class _DelayedCompositeCoordinator:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, request, *, session_id, run_id=None, execution_binding=None):
        del session_id, execution_binding
        self.started.set()
        if not self.release.wait(3):
            raise AssertionError("test coordinator was not released")
        result = build_composite_result_contract(
            request,
            {
                "space": {
                    "domain_id": "gis",
                    "status": "COMPLETED",
                    "result": {
                        "type": "summary_result",
                        "data_profile": {"primary": "metrics", "kinds": ["metrics"]},
                        "views": {"panels": {}},
                    },
                }
            },
            run_id=run_id,
        )
        return {
            "schema_version": "spatial-agent.composite-coordinator.v1",
            "run_id": run_id or "composite-run",
            "status": "COMPLETED",
            "state": "completed",
            "components": result["composite"]["components"],
            "result": result,
        }


def _single_component_request() -> dict[str, object]:
    return {
        "schema_version": "spatial-agent.composite-request.v1",
        "request": "查询空间摘要",
        "components": [
            {
                "component_id": "space",
                "domain_id": "gis",
                "request": "查询空间摘要",
                "planner": "rule",
                "backend": "memory",
            }
        ],
    }


class M303AsyncPollingTests(unittest.TestCase):
    def test_active_composite_snapshot_is_not_projected_as_failed(self):
        coordinator = _DelayedCompositeCoordinator()
        with tempfile.TemporaryDirectory() as root:
            application = CompositeRunApplication(
                coordinator=coordinator,
                state_db_path=str(Path(root) / "runs.db"),
                artifact_root=str(Path(root) / "artifacts"),
                worker_count=1,
            )
            try:
                submitted = application.submit_async(
                    _single_component_request(),
                    session_id="m303-active-snapshot",
                    idempotency_key="m303-active-snapshot-1",
                )
                self.assertTrue(coordinator.started.wait(2))
                active = application.get_run(submitted["run_id"])
                self.assertEqual(active["status"], "PLANNING")
                self.assertEqual(
                    active["result"]["composite"]["state"], "pending"
                )
                self.assertEqual(
                    active["result"]["composite"]["components"][0]["state"],
                    "pending",
                )
                coordinator.release.set()
                deadline = time.time() + 3
                while time.time() < deadline:
                    if application.get_observability(submitted["run_id"])["status"] == "COMPLETED":
                        break
                    time.sleep(0.01)
                self.assertEqual(application.get_run(submitted["run_id"])["status"], "COMPLETED")
            finally:
                coordinator.release.set()
                application.close()


if __name__ == "__main__":
    unittest.main()
