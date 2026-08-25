"""Compact M294 contract: validated plans stay identical through execution."""

from __future__ import annotations

import copy
import tempfile
import time
import unittest
from pathlib import Path

from agent.application.composite import CompositeApplication, CompositeCoordinatorError
from agent.application.composite_runs import CompositeRunApplication
from agent.composite_contract import build_composite_result_contract
from agent.models import PlanStep, TaskPlan
from agent.runtime_core.execution_binding import (
    ExecutionBindingError,
    build_execution_binding,
    project_execution_binding,
    validate_execution_binding,
)


def _request() -> dict:
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


def _binding() -> dict:
    plan = TaskPlan(
        goal="读取空间摘要",
        steps=[PlanStep("summary", "read_summary", {"dataset": "demo"})],
        output={"type": "summary_result"},
        assumptions=[],
    )
    request = _request()
    normalized = copy.deepcopy(request)
    # build_execution_binding normalizes and computes the request identity.
    return build_execution_binding(
        normalized,
        [dict(request["components"][0], capability_id="space_summary")],
        task_plan_bridge={
            "state": "accepted",
            "components": [
                {
                    "component_id": "space",
                    "policy": {
                        "allowed_tools": ["read_summary"],
                        "result_types": ["summary_result"],
                        "max_steps": 4,
                    },
                    "_validated_task_plan": plan,
                    "_execution_workflow": {"template_id": "space_summary"},
                }
            ],
        },
        planner_name="rule",
        backend="memory",
    )


class _Selection:
    domain_id = "gis"


class _Service:
    def __init__(self, *, drift: bool = False):
        self.calls = []
        self.drift = drift

    def run(self, **kwargs):
        self.calls.append(kwargs)
        plan = kwargs.get("validated_plan")
        if plan is None:
            raise AssertionError("coordinator must pass the validated plan")
        result_type = "other_result" if self.drift else plan.output["type"]
        return {
            "run_id": "gis-run",
            "domain_id": "gis",
            "status": "COMPLETED",
            "result": {
                "type": result_type,
                "data_profile": {"primary": "metrics", "kinds": ["metrics"]},
                "views": {"panels": {}},
            },
        }


class _Host:
    def __init__(self, service):
        self.service_value = service

    def select(self, domain_id, *, source="explicit"):
        if domain_id != "gis":
            raise ValueError("domain unavailable")
        return _Selection()

    def service(self, selection):
        return self.service_value


class _BoundCoordinator:
    def __init__(self):
        self.bindings = []

    def run(self, request, *, session_id, run_id=None, execution_binding=None):
        self.bindings.append(execution_binding)
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
            execution_binding=project_execution_binding(execution_binding),
        )
        return {
            "schema_version": "spatial-agent.composite-coordinator.v1",
            "run_id": run_id or "composite-run",
            "status": "COMPLETED",
            "state": "completed",
            "components": result["composite"]["components"],
            "result": result,
        }


class M294ExecutionBindingTests(unittest.TestCase):
    def test_binding_rejects_plan_and_tool_drift(self):
        binding = _binding()
        changed = copy.deepcopy(binding)
        changed["components"][0]["plan"]["steps"][0]["tool"] = "invented_tool"
        with self.assertRaises(ExecutionBindingError):
            validate_execution_binding(changed, request=_request())

        changed = copy.deepcopy(binding)
        changed["components"][0]["plan"]["output"]["type"] = "other_result"
        with self.assertRaises(ExecutionBindingError):
            validate_execution_binding(changed, request=_request())

    def test_coordinator_executes_the_bound_plan_and_publishes_identity(self):
        service = _Service()
        response = CompositeApplication(
            host=_Host(service),
            require_execution_binding=True,
        ).run(_request(), execution_binding=_binding())
        self.assertEqual(response["status"], "COMPLETED")
        self.assertEqual(service.calls[0]["validated_plan"].steps[0].tool, "read_summary")
        execution = response["result"]["composite"]["components"][0]["execution"]
        self.assertEqual(execution["binding_fingerprint"], _binding()["binding_fingerprint"])

    def test_completed_child_result_type_drift_is_rejected(self):
        with self.assertRaises(CompositeCoordinatorError) as context:
            CompositeApplication(
                host=_Host(_Service(drift=True)),
                require_execution_binding=True,
            ).run(_request(), execution_binding=_binding())
        self.assertEqual(context.exception.code, "execution_binding_result_type_mismatch")

    def test_sync_async_and_recovered_result_keep_binding_projection(self):
        coordinator = _BoundCoordinator()
        binding = _binding()
        with tempfile.TemporaryDirectory() as root:
            app = CompositeRunApplication(
                coordinator=coordinator,
                state_db_path=str(Path(root) / "runs.db"),
                artifact_root=str(Path(root) / "artifacts"),
                worker_count=1,
            )
            try:
                sync = app.run(_request(), execution_binding=binding, export_artifact=True)
                async_result = app.submit_async(
                    _request(),
                    execution_binding=binding,
                    idempotency_key="m294-binding",
                    export_artifact=True,
                )
                deadline = time.time() + 3
                while time.time() < deadline:
                    if app.get_observability(async_result["run_id"])["status"] == "COMPLETED":
                        break
                    time.sleep(0.01)
                async_detail = app.get_run(async_result["run_id"])
                self.assertEqual(
                    sync["result"]["composite"]["request"]["execution_binding"]["binding_fingerprint"],
                    async_detail["result"]["composite"]["request"]["execution_binding"]["binding_fingerprint"],
                )
                self.assertEqual(len(coordinator.bindings), 2)
            finally:
                app.close()


if __name__ == "__main__":
    unittest.main()
