"""M166: request and plan identity survive cross-entry projection."""

from __future__ import annotations

import copy
import tempfile
import time
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.request_identity import (
    REQUEST_IDENTITY_SCHEMA_VERSION,
    build_request_identity,
)
from agent.service import AgentService
from agent.service_async import build_async_result_evidence
from domains.text.runtime import build_text_runtime
from evaluation.contract_harness import compare_results, normalize_result
from result_contract import build_result_contract


def _payload(request="查询行政区边界"):
    return {
        "request": request,
        "resolved_request": request,
        "session_id": "conversation-1",
        "planner": "rule",
        "backend": "memory",
        "workflow": None,
        "spatial_context": None,
        "status": "COMPLETED",
        "answer": "完成",
        "steps": [],
        "trace_summary": [],
        "plan": {
            "goal": "查询行政区边界",
            "steps": [],
            "output": {"type": "admin_area_result"},
        },
        "plan_evidence": {
            "plan_identity": {
                "version": "spatial-agent.plan-identity.v1",
                "fingerprint": "sha256:plan-a",
            }
        },
        "result_type": "admin_area_result",
    }


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


def _wait_for_terminal(service, run_id, timeout=8.0):
    terminal = {
        "COMPLETED",
        "WAITING_FOR_DECISION",
        "REJECTED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
        "NEEDS_CLARIFICATION",
    }
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = service.get_run(run_id)
        if payload.get("status") in terminal:
            return payload
        time.sleep(0.01)
    raise AssertionError("async run did not reach a terminal state")


class M166RequestIdentityTests(unittest.TestCase):
    def test_interaction_preserves_original_turn_and_resolved_context(self):
        with tempfile.TemporaryDirectory(prefix="m166-multiturn-") as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            try:
                service.run(
                    request="分析空间数据",
                    session_id="m166-multiturn",
                    planner="rule",
                    backend="memory",
                )
                follow_up = service.run(
                    request="洪山区",
                    session_id="m166-multiturn",
                    planner="rule",
                    backend="memory",
                )
                continued = service.apply_run_interaction(
                    follow_up["run_id"],
                    "provide_facts",
                    {
                        "workflow": {
                            "template_id": "spatial_overview",
                            "constraints": {},
                        },
                        "facts": {"admin_name": "洪山区"},
                    },
                    planner="rule",
                    backend="memory",
                )
            finally:
                service.close()

        self.assertEqual(follow_up["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(continued["request"], "洪山区")
        self.assertEqual(continued["resolved_request"], "洪山区 分析空间数据")

    def test_select_workflow_consumes_pending_request_context(self):
        with tempfile.TemporaryDirectory(prefix="m166-selection-") as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            try:
                initial = service.run(
                    request="分析空间数据",
                    session_id="m166-selection-source",
                    planner="rule",
                    backend="memory",
                )
                selected = service.apply_run_interaction(
                    initial["run_id"],
                    "select_workflow",
                    {
                        "workflow": {
                            "template_id": "spatial_overview",
                            "constraints": {"admin_name": "洪山区"},
                        }
                    },
                    planner="rule",
                    backend="memory",
                )
            finally:
                service.close()

        self.assertEqual(selected["status"], "WAITING_FOR_DECISION")
        self.assertEqual(selected["resolved_request"], "分析空间数据")
        self.assertNotIn("分析空间数据 分析空间数据", selected["resolved_request"])

    def test_provide_facts_preserves_request_identity_of_direct_workflow_run(self):
        workflow = {
            "template_id": "spatial_overview",
            "constraints": {"admin_name": "洪山区"},
        }
        with tempfile.TemporaryDirectory(prefix="m166-interaction-") as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            try:
                initial = service.run(
                    request="分析空间数据",
                    session_id="m166-interaction-source",
                    planner="rule",
                    backend="memory",
                )
                self.assertEqual(initial["status"], "NEEDS_CLARIFICATION")

                continued = service.apply_run_interaction(
                    initial["run_id"],
                    "provide_facts",
                    {
                        "workflow": {
                            "template_id": "spatial_overview",
                            "constraints": {},
                        },
                        "facts": {"admin_name": "洪山区"},
                    },
                    planner="rule",
                    backend="memory",
                )
                direct = service.run(
                    request="分析空间数据",
                    session_id="m166-interaction-direct",
                    planner="rule",
                    backend="memory",
                    workflow=workflow,
                    require_confirmation=True,
                    export_artifact=True,
                )
            finally:
                service.close()

        continued_result = continued["result"]
        direct_result = direct["result"]
        self.assertEqual(continued["resolved_request"], "分析空间数据")
        self.assertEqual(
            continued_result["request_identity"],
            direct_result["request_identity"],
        )
        self.assertEqual(
            continued_result["planning"]["plan_identity"],
            direct_result["planning"]["plan_identity"],
        )
        self.assertEqual(compare_results([continued, direct]), [])

    def test_request_identity_ignores_transport_configuration(self):
        first = build_request_identity(_payload())
        changed = _payload()
        changed["session_id"] = "another-session"
        changed["planner"] = "openai"
        changed["backend"] = "local"
        second = build_request_identity(changed)
        self.assertEqual(first["schema_version"], REQUEST_IDENTITY_SCHEMA_VERSION)
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertNotEqual(
            first["fingerprint"], build_request_identity(_payload("另一个问题"))["fingerprint"]
        )

    def test_result_and_async_evidence_share_request_and_plan_identity(self):
        payload = _payload()
        contract = build_result_contract(payload)
        evidence = build_async_result_evidence(contract, status="COMPLETED")
        self.assertEqual(
            contract["request_identity"], evidence["request_identity"]
        )
        self.assertEqual(
            contract["planning"]["plan_identity"]["fingerprint"],
            evidence["planning"]["plan_identity"]["fingerprint"],
        )

    def test_harness_reports_plan_identity_drift_but_ignores_request_transport(self):
        first = _payload()
        second = copy.deepcopy(first)
        second["session_id"] = "another-session"
        second["planner"] = "openai"
        second["plan_evidence"]["plan_identity"]["fingerprint"] = "sha256:plan-b"
        first_contract = build_result_contract(first)
        second_contract = build_result_contract(second)
        first["result"] = first_contract
        second["result"] = second_contract
        self.assertEqual(
            normalize_result(first).as_dict()["request_identity"],
            normalize_result(second).as_dict()["request_identity"],
        )
        differences = compare_results([first, second])
        self.assertTrue(
            any("$.plan_identity_fingerprint" in item for item in differences),
            differences,
        )

    def test_async_harness_projection_keeps_both_identities(self):
        payload = _payload()
        contract = build_result_contract(payload)
        payload["result"] = contract
        payload["async_result_evidence"] = build_async_result_evidence(
            contract, status="COMPLETED"
        )
        projection = normalize_result(payload).as_dict()
        self.assertEqual(
            projection["request_identity"],
            projection["async_result_evidence"]["request_identity"],
        )
        self.assertEqual(
            contract["planning"]["plan_identity"],
            projection["async_result_evidence"]["plan_identity"],
        )

    def test_sqlite_artifact_recovery_preserves_identity(self):
        with tempfile.TemporaryDirectory(prefix="m166-identity-") as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            first = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=artifacts,
                runtime_factory=_text_runtime_factory,
            )
            try:
                submitted = first.run_async(
                    request="请摘要一段异步文本，并在执行前确认。",
                    session_id="m166-identity",
                    planner="rule",
                    backend="memory",
                    spatial_context={"admin_name": "测试区"},
                    require_confirmation=True,
                    export_artifact=True,
                    idempotency_key="m166-identity-key",
                )
                waiting = _wait_for_terminal(first, submitted["run_id"])
                observation = first.get_async_observability(submitted["run_id"])
                artifact = artifacts.read_run(submitted["run_id"], domain_id="text")
            finally:
                first.close()

            recovered_service = AgentService(
                state_db_path=str(root / "empty-state.db"),
                artifact_store=artifacts,
                runtime_factory=_text_runtime_factory,
            )
            try:
                recovered = recovered_service.get_run(submitted["run_id"])
                recovered_observation = recovered_service.get_async_observability(
                    submitted["run_id"]
                )
            finally:
                recovered_service.close()

        expected_request = waiting["result"]["request_identity"]
        expected_plan = waiting["result"]["planning"]["plan_identity"]
        self.assertEqual(expected_request["schema_version"], REQUEST_IDENTITY_SCHEMA_VERSION)
        for label, value in (
            ("async observation", observation["result_evidence"]["request_identity"]),
            ("artifact async evidence", artifact["async_result_evidence"]["request_identity"]),
            ("recovered result", recovered["result"]["request_identity"]),
            ("recovered async observation", recovered_observation["result_evidence"]["request_identity"]),
        ):
            self.assertEqual(value, expected_request, label)
        self.assertEqual(
            observation["result_evidence"]["planning"]["plan_identity"],
            expected_plan,
        )
        self.assertEqual(
            artifact["async_result_evidence"]["planning"]["plan_identity"],
            expected_plan,
        )
        self.assertEqual(
            recovered["result"]["planning"]["plan_identity"],
            expected_plan,
        )
        self.assertEqual(
            recovered_observation["result_evidence"]["planning"]["plan_identity"],
            expected_plan,
        )


if __name__ == "__main__":
    unittest.main()
