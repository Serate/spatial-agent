"""M218: compare semantic results without transport-only drift."""

from __future__ import annotations

from copy import deepcopy
import unittest
import tempfile
import time
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.deployment_evidence import build_deployment_evidence
from agent.service import AgentService
from domains.text.runtime import build_text_runtime
from evaluation.contract_harness import compare_core_results, normalize_core_result


def _payload() -> dict:
    return {
        "status": "COMPLETED",
        "answer": "已完成分析。",
        "run_id": "run-a",
        "result": {
            "type": "spatial_analysis_result",
            "title": "空间分析",
            "planning": {
                "source": "rule",
                "selected_capability_id": "spatial_analysis",
                "capability_candidate_ids": ["spatial_analysis"],
                "plan_identity": {
                    "version": "spatial-agent.plan-identity.v1",
                    "fingerprint": "sha256:plan-a",
                },
            },
            "lineage": {"artifact": {"available": True}},
            "views": {
                "schema_version": "spatial-agent.views.v1",
                "panels": {"answer": {"kind": "answer", "state": "available"}},
            },
        },
    }


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


def _wait_for_terminal(service: AgentService, run_id: str) -> dict:
    terminal = {
        "COMPLETED",
        "WAITING_FOR_DECISION",
        "REJECTED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
        "NEEDS_CLARIFICATION",
    }
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        payload = service.get_run(run_id)
        if payload.get("status") in terminal:
            return payload
        time.sleep(0.01)
    raise AssertionError("async run did not reach a terminal state")


class M218CoreContractTests(unittest.TestCase):
    def test_core_contract_ignores_transport_and_artifact_presence(self):
        first = _payload()
        second = deepcopy(first)
        second["run_id"] = "run-b"
        second["result"]["lineage"]["artifact"] = {"available": False}
        second["execution_record"] = {
            "kind": "run",
            "run_id": "run-b",
            "attempt": 2,
        }
        second["async_result_evidence"] = {
            "schema_version": "spatial-agent.async-result-evidence.v1",
            "state": "success",
        }

        self.assertEqual(compare_core_results([first, second]), [])
        normalized = normalize_core_result(first).as_dict()
        self.assertEqual(normalized["result_type"], "spatial_analysis_result")
        self.assertNotIn("execution", normalized)
        self.assertNotIn("async_result_evidence", normalized)
        self.assertNotIn("artifact_available", normalized)

    def test_core_contract_still_reports_semantic_drift(self):
        changed = _payload()
        changed["answer"] = "另一份结论。"
        changed["result"]["planning"]["selected_capability_id"] = "other"

        differences = compare_core_results([_payload(), changed])

        self.assertTrue(any("$.answer" in item for item in differences))
        self.assertTrue(
            any("$.selected_capability" in item for item in differences)
        )

    def test_sync_async_artifact_and_sqlite_share_core_contract(self):
        request = "请摘要一段文本并保留结构化证据。"
        with tempfile.TemporaryDirectory(prefix="m218-core-") as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=artifacts,
                runtime_factory=_text_runtime_factory,
            )
            try:
                sync = service.run(
                    request=request,
                    session_id="m218-core",
                    planner="rule",
                    backend="memory",
                    export_artifact=True,
                )
                submitted = service.run_async(
                    request=request,
                    session_id="m218-core-async",
                    planner="rule",
                    backend="memory",
                    export_artifact=True,
                    idempotency_key="m218-core-key",
                )
                async_result = _wait_for_terminal(service, submitted["run_id"])
            finally:
                service.close()

            sync_artifact = artifacts.read_run(sync["run_id"], domain_id="text")
            async_artifact = artifacts.read_run(
                submitted["run_id"], domain_id="text"
            )

        self.assertEqual(sync["status"], "COMPLETED")
        self.assertEqual(async_result["status"], "COMPLETED")
        self.assertEqual(
            compare_core_results(
                [sync, async_result, sync_artifact, async_artifact]
            ),
            [],
        )

    def test_result_warning_does_not_become_deployment_degraded(self):
        evidence = build_deployment_evidence(
            {"runtime_context": {"domain_id": "text", "planner": "rule"}},
            degradation={"status": "warning", "item_count": 1},
        )

        self.assertEqual(evidence["status"], "context_only")
        self.assertEqual(evidence["degradation"]["status"], "warning")


if __name__ == "__main__":
    unittest.main()
