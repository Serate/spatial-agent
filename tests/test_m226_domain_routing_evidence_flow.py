"""M226: Domain routing evidence crosses Service and persistence boundaries."""

from __future__ import annotations

import hashlib
import tempfile
import time
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.domain_routing_evidence import (
    DomainRoutingEvidenceError,
    build_domain_routing_evidence,
)
from agent.domain_selection import DomainSelection
from agent.domain_selector import DomainRoutingCandidate, DomainRoutingDecision
from agent.service import AgentService
from agent.sqlite_store import SQLiteStateStore


def _routing_evidence(request: str, decision_id: str, domain_id: str = "text"):
    decision = DomainRoutingDecision(
        decision_id=decision_id,
        status="selected",
        reason_code="explicit_domain",
        selector_id="fixture.v1",
        request_fingerprint=hashlib.sha256(request.encode("utf-8")).hexdigest(),
        candidates=(DomainRoutingCandidate(domain_id, domain_id, score=100),),
        selection=DomainSelection(domain_id, source="automatic"),
    )
    return build_domain_routing_evidence(decision)


class M226DomainRoutingEvidenceFlowTests(unittest.TestCase):
    def _service(self, root: Path) -> AgentService:
        return AgentService(
            artifact_store=ArtifactStore(root / "artifacts", legacy_domain_id="text"),
            state_db_path=str(root / "state.db"),
            domain_id="text",
        )

    def _wait_terminal(self, service: AgentService, run_id: str):
        result = None
        for _ in range(200):
            result = service.get_run(run_id)
            if result["status"] not in {"CREATED", "PLANNING", "EXECUTING"}:
                return result
            time.sleep(0.01)
        self.fail("async run did not reach a terminal state: " + str(result))

    def test_sync_sqlite_artifact_and_nested_result_share_bound_evidence(self):
        request = "请摘要这段文本。"
        with tempfile.TemporaryDirectory(prefix="m226-sync-") as directory:
            root = Path(directory)
            service = self._service(root)
            try:
                evidence = _routing_evidence(request, "decision-sync")

                response = service.run(
                    request,
                    session_id="m226-sync",
                    run_id="m226-sync-run",
                    export_artifact=True,
                    _domain_routing_evidence=evidence,
                )
                expected = response["domain_routing_evidence"]

                self.assertTrue(expected["available"])
                self.assertEqual(expected["binding"]["state"], "execution_bound")
                self.assertEqual(expected["binding"]["run_id"], response["run_id"])
                self.assertEqual(response["result"]["domain_routing_evidence"], expected)
                self.assertEqual(
                    SQLiteStateStore(
                        str(root / "state.db"), legacy_domain_id="text"
                    ).get(response["run_id"], domain_id="text").to_dict()[
                        "domain_routing_evidence"
                    ],
                    expected,
                )
                artifact = service._artifact_store.read_run(
                    response["run_id"], domain_id="text"
                )
                self.assertEqual(artifact["domain_routing_evidence"], expected)
                self.assertEqual(
                    artifact["result"]["domain_routing_evidence"], expected
                )
            finally:
                service.close()

    def test_async_restart_polling_and_idempotency_use_routing_identity(self):
        request = "请摘要这段文本。"
        with tempfile.TemporaryDirectory(prefix="m226-async-") as directory:
            root = Path(directory)
            evidence = _routing_evidence(request, "decision-async-a")
            service = self._service(root)
            submitted = service.run_async(
                request=request,
                session_id="m226-async",
                idempotency_key="m226-routing-key",
                export_artifact=True,
                _domain_routing_evidence=evidence,
            )
            run_id = submitted["run_id"]
            try:
                store = SQLiteStateStore(
                    str(root / "state.db"), legacy_domain_id="text"
                )
                pending = None
                for _ in range(100):
                    pending = store.get(run_id, domain_id="text")
                    if (
                        pending is not None
                        and pending.domain_routing_evidence.get("available") is True
                    ):
                        break
                    time.sleep(0.005)
                self.assertEqual(
                    pending.domain_routing_evidence["binding"]["run_id"], run_id
                )
                with self.assertRaises(DomainRoutingEvidenceError) as captured:
                    service.run_async(
                        request=request,
                        session_id="m226-async",
                        idempotency_key="m226-routing-key",
                        _domain_routing_evidence=_routing_evidence(
                            request, "decision-async-b"
                        ),
                    )
                self.assertEqual(
                    captured.exception.code,
                    "domain_routing_evidence_idempotency_conflict",
                )

                result = self._wait_terminal(service, run_id)
                expected = result["domain_routing_evidence"]
                observation = service.get_async_observability(run_id)
                self.assertEqual(
                    observation["result_evidence"]["domain_routing_evidence"],
                    expected,
                )
            finally:
                service.close()

            restarted = self._service(root)
            try:
                recovered = restarted.get_async_observability(run_id)
                artifact = restarted._artifact_store.read_run(
                    run_id, domain_id="text"
                )
                self.assertEqual(
                    recovered["result_evidence"]["domain_routing_evidence"],
                    expected,
                )
                self.assertEqual(artifact["domain_routing_evidence"], expected)
                self.assertEqual(
                    artifact["async_result_evidence"][
                        "domain_routing_evidence"
                    ],
                    expected,
                )
            finally:
                restarted.close()

    def test_direct_run_is_explicitly_unavailable_and_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="m226-compat-") as directory:
            service = self._service(Path(directory))
            try:
                direct = service.run("请摘要这段文本。", session_id="m226-direct")
                self.assertFalse(direct["domain_routing_evidence"]["available"])
                self.assertEqual(
                    direct["result"]["domain_routing_evidence"],
                    direct["domain_routing_evidence"],
                )
                with self.assertRaises(DomainRoutingEvidenceError) as captured:
                    service.run(
                        "请摘要这段文本。",
                        session_id="m226-mismatch",
                        _domain_routing_evidence=_routing_evidence(
                            "请摘要这段文本。", "decision-gis", domain_id="gis"
                        ),
                    )
                self.assertEqual(
                    captured.exception.code, "domain_routing_evidence_domain_mismatch"
                )
            finally:
                service.close()

    def test_sync_run_identity_conflict_and_forced_resume_are_safe(self):
        request = "请摘要这段文本。"
        with tempfile.TemporaryDirectory(prefix="m226-sync-identity-") as directory:
            service = self._service(Path(directory))
            try:
                first = service.run(
                    request,
                    session_id="m226-sync-identity",
                    run_id="m226-stable-run",
                    _domain_routing_evidence=_routing_evidence(
                        request,
                        "decision-stable",
                    ),
                )
                resumed = service.run(
                    request,
                    session_id="m226-sync-identity",
                    run_id="m226-stable-run",
                    _force_run_id=True,
                )
                self.assertEqual(
                    resumed["domain_routing_evidence"],
                    first["domain_routing_evidence"],
                )
                with self.assertRaises(DomainRoutingEvidenceError) as captured:
                    service.run(
                        request,
                        session_id="m226-sync-identity",
                        run_id="m226-stable-run",
                        _domain_routing_evidence=_routing_evidence(
                            request,
                            "decision-conflict",
                        ),
                    )
                self.assertEqual(
                    captured.exception.code,
                    "domain_routing_evidence_run_conflict",
                )
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
