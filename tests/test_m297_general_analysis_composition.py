import os
import tempfile
import time
import unittest

from agent.application.composite_runs import CompositeRunApplication
from agent.application.composite_contract import (
    CompositeContractError,
    build_composite_result_contract,
    normalize_composite_request,
)
from agent.application.composite_planner import CompositePlannerError, normalize_composite_plan
from agent.application.composite_view import build_composite_view_projection
from agent.runtime_core.composition import (
    COMPOSITION_SCHEMA_VERSION,
    normalize_component_inputs,
)


def _context(*, producer_kinds=("vector",)):
    return {
        "capability_index": [
            {
                "domain_id": "gis",
                "capability_id": "boundary",
                "available": True,
                "execution_ready": True,
                "output_profiles": [
                    {
                        "result_type": "admin_area_result",
                        "primary": producer_kinds[0],
                        "kinds": list(producer_kinds),
                    }
                ],
            },
            {
                "domain_id": "economic",
                "capability_id": "trend",
                "available": True,
                "execution_ready": True,
                "output_profiles": [
                    {
                        "result_type": "economic_timeseries_result",
                        "primary": "timeseries",
                        "kinds": ["timeseries", "metrics"],
                    }
                ],
            },
        ]
    }


def _payload(*, accepted_kinds=("vector",)):
    return {
        "outcome": "success",
        "goal": "组合分析",
        "message": "",
        "components": [
            {
                "component_id": "boundary",
                "domain_id": "gis",
                "capability_id": "boundary",
                "request": "查询区域边界",
                "depends_on": [],
                "required": True,
            },
            {
                "component_id": "trend",
                "domain_id": "economic",
                "capability_id": "trend",
                "request": "分析趋势",
                "depends_on": ["boundary"],
                "required": True,
                "inputs": [
                    {
                        "name": "region_boundary",
                        "source": {"component_id": "boundary", "path": "result"},
                        "accepted_kinds": list(accepted_kinds),
                        "required": True,
                    }
                ],
            },
        ],
    }


def _failure_request():
    return {
        "schema_version": "spatial-agent.composite-request.v1",
        "request": "模拟组合执行失败",
        "components": [
            {
                "component_id": "boundary",
                "domain_id": "gis",
                "request": "查询区域边界",
                "depends_on": [],
                "required": True,
            },
            {
                "component_id": "trend",
                "domain_id": "economic",
                "request": "分析区域趋势",
                "depends_on": ["boundary"],
                "required": True,
            },
        ],
    }


class _FailingCoordinator:
    def run(self, request, **kwargs):
        del request, kwargs
        raise RuntimeError("simulated coordinator failure")


class M297CompositionTests(unittest.TestCase):
    def test_input_reference_is_bounded_and_versioned(self):
        value = normalize_component_inputs(_payload()["components"][1]["inputs"])
        self.assertEqual(value[0]["source"]["path"], "result")
        self.assertEqual(value[0]["accepted_kinds"], ["vector"])
        self.assertEqual(COMPOSITION_SCHEMA_VERSION, "spatial-agent.composition.v1")

    def test_input_reference_requires_declared_prior_dependency(self):
        request = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "组合分析",
            "components": [
                {
                    "component_id": "trend",
                    "domain_id": "economic",
                    "request": "分析趋势",
                    "depends_on": [],
                    "inputs": _payload()["components"][1]["inputs"],
                },
                {
                    "component_id": "boundary",
                    "domain_id": "gis",
                    "request": "查询边界",
                },
            ],
        }
        with self.assertRaises(CompositeContractError) as caught:
            normalize_composite_request(request)
        self.assertEqual(caught.exception.code, "composition_input_dependency_missing")

    def test_planner_rejects_incompatible_source_profile(self):
        with self.assertRaises(CompositePlannerError) as caught:
            normalize_composite_plan(
                _payload(accepted_kinds=("raster",)),
                request="组合分析",
                context=_context(),
                planner_source="replay",
            )
        self.assertEqual(caught.exception.code, "composition_input_type_mismatch")

    def test_planner_accepts_type_compatible_cross_domain_reference(self):
        result = normalize_composite_plan(
            _payload(),
            request="组合分析",
            context=_context(),
            planner_source="replay",
        )
        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(result["request"]["components"][1]["inputs"][0]["name"], "region_boundary")

    def test_result_projection_preserves_input_provenance(self):
        request = normalize_composite_request(
            {
                "schema_version": "spatial-agent.composite-request.v1",
                "request": "组合分析",
                "components": _payload()["components"],
            }
        )
        result = build_composite_result_contract(
            request,
            {
                "boundary": {
                    "status": "COMPLETED",
                    "domain_id": "gis",
                    "result": {
                        "type": "admin_area_result",
                        "data_profile": {
                            "schema_version": "spatial-agent.data-profile.v1",
                            "primary": "vector",
                            "kinds": ["vector"],
                        },
                    },
                },
                "trend": {
                    "status": "COMPLETED",
                    "domain_id": "economic",
                    "result": {
                        "type": "economic_timeseries_result",
                        "data_profile": {
                            "schema_version": "spatial-agent.data-profile.v1",
                            "primary": "timeseries",
                            "kinds": ["timeseries", "metrics"],
                        },
                    },
                },
            },
        )
        component = next(item for item in result["composite"]["components"] if item["component_id"] == "trend")
        self.assertEqual(component["inputs"][0]["source"]["component_id"], "boundary")

    def test_view_projection_exposes_cross_type_result_kinds(self):
        request = normalize_composite_request(
            {
                "schema_version": "spatial-agent.composite-request.v1",
                "request": "组合分析",
                "components": _payload()["components"],
            }
        )
        result = build_composite_result_contract(
            request,
            {
                "boundary": {
                    "status": "COMPLETED",
                    "domain_id": "gis",
                    "result": {
                        "type": "admin_area_result",
                        "data_profile": {
                            "schema_version": "spatial-agent.data-profile.v1",
                            "primary": "vector",
                            "kinds": ["vector"],
                        },
                    },
                },
                "trend": {
                    "status": "COMPLETED",
                    "domain_id": "economic",
                    "result": {
                        "type": "economic_timeseries_result",
                        "data_profile": {
                            "schema_version": "spatial-agent.data-profile.v1",
                            "primary": "timeseries",
                            "kinds": ["timeseries", "metrics"],
                        },
                    },
                },
            },
        )
        projection = build_composite_view_projection(result)
        self.assertEqual(projection["data_kinds"], ["vector", "metrics", "timeseries"])
        trend = next(
            item for item in projection["sections"] if item.get("component_id") == "trend"
        )
        self.assertEqual(trend["data_kinds"], ["metrics", "timeseries"])

    def test_async_worker_failure_remains_readable_as_composite_result(self):
        """A failed worker must not make polling or the View seam crash."""
        with tempfile.TemporaryDirectory() as directory:
            application = CompositeRunApplication(
                coordinator=_FailingCoordinator(),
                state_db_path=os.path.join(directory, "state.sqlite"),
                artifact_root=os.path.join(directory, "artifacts"),
            )
            try:
                submitted = application.submit_async(
                    _failure_request(),
                    idempotency_key="m297-worker-failure",
                )
                deadline = time.monotonic() + 2
                observation = None
                while time.monotonic() < deadline:
                    observation = application.get_observability(submitted["run_id"])
                    if observation["status"] == "FAILED":
                        break
                    time.sleep(0.01)
                self.assertIsNotNone(observation)
                self.assertEqual(observation["status"], "FAILED")

                detail = application.get_run(submitted["run_id"])
                self.assertEqual(detail["status"], "FAILED")
                self.assertEqual(detail["error_code"], "execution_failed")
                self.assertEqual(detail["result"]["type"], "composite_result")
                self.assertEqual(detail["result"]["composite"]["state"], "failed")
                self.assertEqual(detail["view"]["state"], "failed")
            finally:
                application.close()


if __name__ == "__main__":
    unittest.main()
