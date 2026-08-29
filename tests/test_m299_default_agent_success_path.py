"""Compact M299 contract tests for the default Agent provider boundary."""

import json
import threading
import tempfile
import time
import unittest

from agent.artifact_store import ArtifactStore
from agent.application.composite_planning import CompositePlanningApplication
from agent.application.composite_runs import (
    CompositeRunApplication,
    _safe_planning_evidence,
)
from agent.application.composite_contract import build_composite_result_contract
from agent.application.composite_planner import LLMCompositePlanner
from agent.application.composite_view import build_composite_view_projection
from agent.runtime_core.planner_envelope import (
    PLANNER_ENVELOPE_LAYERS,
    PLANNER_ENVELOPE_SCHEMA_VERSION,
    PlannerEnvelopeError,
    build_planner_envelope,
)
from agent.runtime_core.selection_evidence import (
    SELECTION_EVIDENCE_SCHEMA_VERSION,
    normalize_selection_evidence,
    project_selection_evidence,
)


def _context():
    return {
        "schema_version": "spatial-agent.composite-request-context.v2",
        "planner": "openai",
        "backend": "local",
        "request_fingerprint": "m299-request",
        "request_summary": "分析洪山区近年经济与空间变化",
        "domain_contexts": [
            {
                "domain_id": "economic",
                "facts": {
                    "schema_version": "facts.v1",
                    "admin_name": "洪山区",
                    "tasks": ["trend"],
                    "datasets": ["economic_indicators"],
                    "constraints": {"time_range": "近五年"},
                    "source_path": "D:/private/secret.csv",
                },
                "data_readiness": {"status": "ready"},
                "clarification": {"state": "not_required"},
                "discovery": {"selected_capability_id": "trend"},
            }
        ],
        "capability_index": [
            {
                "domain_id": "economic",
                "capability_id": "trend",
                "selection_key": "economic::trend",
                "label": "趋势分析",
                "description": "计算已登记指标的时间趋势",
                "available": True,
                "datasets": ["economic_indicators"],
                "result_types": ["economic_timeseries_result"],
                "output_profiles": [
                    {
                        "result_type": "economic_timeseries_result",
                        "primary": "timeseries",
                        "kinds": ["timeseries", "metrics"],
                    }
                ],
                "workflow_ids": ["economic-trend"],
                "tools": ["query_indicator", "calculate_trend"],
                "execution_ready": True,
            },
            {
                "domain_id": "gis",
                "capability_id": "boundary",
                "selection_key": "gis::boundary",
                "label": "区域边界",
                "description": "查询已登记行政区边界",
                "available": True,
                "datasets": ["admin_boundaries"],
                "result_types": ["admin_area_result"],
                "output_profiles": [
                    {
                        "result_type": "admin_area_result",
                        "primary": "vector",
                        "kinds": ["vector"],
                    }
                ],
                "workflow_ids": ["gis-boundary"],
                "tools": ["get_admin_boundary"],
                "execution_ready": True,
            },
        ],
        "workflow_index": [
            {
                "domain_id": "economic",
                "workflow_id": "economic-trend",
                "label": "指标趋势",
                "allowed_tools": ["query_indicator", "calculate_trend"],
                "result_types": ["economic_timeseries_result"],
            },
            {
                "domain_id": "economic",
                "workflow_id": "unrelated-workflow",
                "label": "不相关流程",
                "allowed_tools": ["private_tool"],
                "result_types": ["private_result"],
            },
        ],
        "discovery": {
            "state": "available",
            "reason_code": "candidates_available",
            "candidates": [{"state": "available", "domain_id": "economic", "capability_id": "trend"}],
            "next_actions": ["plan"],
        },
        "clarification": {
            "state": "not_required",
            "reason_code": "facts_and_candidates_available",
            "message": "已具备规划所需信息。",
        },
    }


class _Client:
    def __init__(self):
        self.messages = None

    def complete_json(self, messages, schema):
        self.messages = messages
        return {
            "outcome": "needs_clarification",
            "goal": "",
            "message": "请指定要比较的经济指标。",
            "components": [],
        }


class _Coordinator:
    def run(self, request, *, session_id, run_id=None):
        del session_id
        result = build_composite_result_contract(
            request,
            {
                "economic-query": {
                    "status": "COMPLETED",
                    "domain_id": "economic",
                    "result": {
                        "type": "economic_metrics_result",
                        "data_profile": {"primary": "metrics", "kinds": ["metrics"]},
                    },
                }
            },
            run_id=run_id,
        )
        return {
            "run_id": run_id or "m299-composite-run",
            "status": "COMPLETED",
            "result": result,
        }


def _execution_request():
    return {
        "schema_version": "spatial-agent.composite-request.v1",
        "request": "查询洪山区地区生产总值",
        "components": [
            {
                "component_id": "economic-query",
                "domain_id": "economic",
                "request": "查询洪山区地区生产总值",
                "depends_on": [],
                "required": True,
            }
        ],
    }


class _BlockingArtifactStore(ArtifactStore):
    """Hold publication to expose a premature COMPLETED snapshot."""

    def __init__(self, root):
        super().__init__(root, legacy_domain_id="composite")
        self.entered = threading.Event()
        self.release = threading.Event()

    def write_run(self, payload):
        self.entered.set()
        if not self.release.wait(timeout=3):
            raise AssertionError("artifact publication did not release")
        return super().write_run(payload)


class M299DefaultAgentSuccessPathTests(unittest.TestCase):
    def test_envelope_has_four_layers_and_redacts_private_context(self):
        envelope = build_planner_envelope(_context())
        encoded = json.dumps(envelope, ensure_ascii=False)

        self.assertEqual(envelope["schema_version"], PLANNER_ENVELOPE_SCHEMA_VERSION)
        self.assertEqual(envelope["layers"], list(PLANNER_ENVELOPE_LAYERS))
        self.assertTrue(envelope["redaction"]["applied"])
        self.assertNotIn("source_path", encoded)
        self.assertEqual(
            envelope["selection"]["selected_capability_keys"], ["economic::trend"]
        )

    def test_execution_layer_only_includes_candidate_workflows(self):
        envelope = build_planner_envelope(_context())
        workflows = envelope["execution_contract"]["workflows"]

        self.assertEqual([item["workflow_id"] for item in workflows], ["economic-trend"])
        self.assertEqual(
            envelope["execution_contract"]["capabilities"][0]["capability_id"],
            "trend",
        )

    def test_llm_receives_envelope_instead_of_raw_context(self):
        client = _Client()
        result = LLMCompositePlanner(client).plan("分析洪山区", context=_context())

        self.assertEqual(result["status"], "NEEDS_CLARIFICATION")
        self.assertIn("[Trusted planner envelope]", client.messages[1]["content"])
        self.assertIn(PLANNER_ENVELOPE_SCHEMA_VERSION, client.messages[1]["content"])
        self.assertNotIn("D:/private/secret.csv", client.messages[1]["content"])

    def test_envelope_budget_is_fail_closed(self):
        with self.assertRaises(PlannerEnvelopeError) as raised:
            build_planner_envelope(_context(), max_bytes=128)
        self.assertEqual(raised.exception.code, "planner_envelope_too_large")

    def test_selection_evidence_keeps_identity_readiness_and_next_action(self):
        evidence = project_selection_evidence(
            _context(),
            existing_selection={
                "state": "selected",
                "selected_source": "llm",
                "selected_capability_ids": ["trend"],
                "selected_capability_keys": ["economic::trend"],
            },
        )

        self.assertEqual(evidence["schema_version"], SELECTION_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(evidence["selected_capability_keys"], ["economic::trend"])
        self.assertEqual(evidence["candidates"][0]["execution_ready"], True)
        self.assertEqual(evidence["next_actions"], ["plan"])

    def test_planning_attach_injects_selection_evidence_into_public_result(self):
        result = CompositePlanningApplication._attach_context(
            {
                "planner_evidence": {
                    "selection": {
                        "state": "selected",
                        "selected_source": "llm",
                        "selected_capability_ids": ["trend"],
                        "selected_capability_keys": ["economic::trend"],
                    }
                }
            },
            _context(),
        )

        self.assertEqual(
            result["planner_evidence"]["selection_evidence"]["schema_version"],
            SELECTION_EVIDENCE_SCHEMA_VERSION,
        )

    def test_selection_evidence_survives_safe_persistence_projection(self):
        projected = project_selection_evidence(
            _context(),
            existing_selection={
                "state": "selected",
                "selected_capability_keys": ["economic::trend"],
            },
        )
        restored = normalize_selection_evidence(projected)
        self.assertEqual(restored["selected_capability_keys"], ["economic::trend"])
        self.assertEqual(restored["candidates"][0]["label"], "趋势分析")

    def test_selection_evidence_survives_composite_view_projection(self):
        evidence = project_selection_evidence(
            _context(),
            existing_selection={
                "state": "selected",
                "selected_capability_keys": ["economic::trend"],
            },
        )
        safe = _safe_planning_evidence({"selection_evidence": evidence})
        view = build_composite_view_projection(
            {
                "status": "COMPLETED",
                "planner_evidence": safe,
                "composite": {
                    "state": "completed",
                    "request": {"fingerprint": "m299-view"},
                    "components": [],
                    "evidence": {},
                },
            }
        )

        self.assertEqual(
            view["planning"]["selection_evidence"]["selected_capability_keys"],
            ["economic::trend"],
        )

    def test_selection_evidence_survives_sync_async_and_restart_views(self):
        with tempfile.TemporaryDirectory() as directory:
            db = directory + "/runs.sqlite"
            artifacts = directory + "/artifacts"
            evidence = project_selection_evidence(
                _context(),
                existing_selection={
                    "state": "selected",
                    "selected_capability_keys": ["economic::trend"],
                },
            )
            application = CompositeRunApplication(
                coordinator=_Coordinator(),
                state_db_path=db,
                artifact_root=artifacts,
                worker_count=1,
            )
            try:
                request = _execution_request()
                sync = application.run_with_planning(
                    request,
                    session_id="m299-sync-view",
                    export_artifact=True,
                    planner_evidence={"selection_evidence": evidence},
                )
                self.assertEqual(
                    sync["view"]["planning"]["selection_evidence"]["state"],
                    "selected",
                )
                queued = application.submit_async_with_planning(
                    request,
                    session_id="m299-async-view",
                    idempotency_key="m299-async-view",
                    export_artifact=True,
                    planner_evidence={"selection_evidence": evidence},
                )
                deadline = time.time() + 3
                detail = {}
                while time.time() < deadline:
                    detail = application.get_run(queued["run_id"])
                    if detail.get("status") == "COMPLETED":
                        break
                    time.sleep(0.01)
                self.assertEqual(
                    detail["view"]["planning"]["selection_evidence"]["state"],
                    "selected",
                )
                artifact_ref = detail.get("artifact_ref")
                self.assertTrue(artifact_ref)
            finally:
                application.close()

            restored = CompositeRunApplication(
                coordinator=_Coordinator(),
                state_db_path=db,
                artifact_root=artifacts,
                worker_count=1,
            )
            try:
                recovered = restored.get_run(queued["run_id"])
                self.assertEqual(
                    recovered["view"]["planning"]["selection_evidence"]["state"],
                    "selected",
                )
            finally:
                restored.close()

    def test_async_completion_is_not_visible_before_artifact_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _BlockingArtifactStore(directory + "/artifacts")
            application = CompositeRunApplication(
                coordinator=_Coordinator(),
                state_db_path=directory + "/runs.sqlite",
                artifact_store=store,
                worker_count=1,
            )
            try:
                queued = application.submit_async(
                    _execution_request(),
                    session_id="m299-artifact-order",
                    idempotency_key="m299-artifact-order",
                    export_artifact=True,
                )
                self.assertTrue(store.entered.wait(timeout=2))
                during_publication = application.get_run(queued["run_id"])
                self.assertFalse(
                    during_publication.get("status") == "COMPLETED"
                    and not during_publication.get("artifact_ref")
                )
                store.release.set()
                deadline = time.time() + 3
                detail = {}
                while time.time() < deadline:
                    detail = application.get_run(queued["run_id"])
                    if detail.get("status") == "COMPLETED":
                        break
                    time.sleep(0.01)
                self.assertEqual(detail.get("status"), "COMPLETED")
                self.assertTrue(detail.get("artifact_ref"))
            finally:
                store.release.set()
                application.close()

    def test_llm_clarification_is_bound_to_public_next_action(self):
        application = CompositePlanningApplication.__new__(CompositePlanningApplication)
        result = application._normalize_candidate(
            {
                "status": "NEEDS_CLARIFICATION",
                "planner_source": "llm",
                "message": "请指定要比较的指标。",
                "components": [],
            },
            context=_context(),
            planner_name="openai",
            backend="local",
        )

        self.assertEqual(result["clarification"]["state"], "needs_clarification")
        self.assertEqual(result["clarification"]["next_actions"], ["补充信息后重新提交"])


if __name__ == "__main__":
    unittest.main()
