"""M193-B: preview evidence binding gates stale execution."""

from __future__ import annotations

import json
import threading
import unittest
import tempfile
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service_async import (
    build_async_result_evidence,
    normalize_async_result_evidence,
)
from agent.service import AgentService
from domains.text.domain import TextDomainPack
from evaluation.contract_harness import compare_evidence_bindings
from serve_api import AgentApiHandler


class M193EvidenceGateTests(unittest.TestCase):
    def test_preview_and_run_share_evidence_binding(self):
        service = AgentService(domain_pack=TextDomainPack())
        try:
            preview = service.preview(
                "请总结这段文本",
                session_id="m193-binding-preview",
                planner="rule",
                backend="memory",
            )
            binding = preview["plan_evidence"]["evidence_binding"]
            completed = service.run(
                "请总结这段文本",
                session_id="m193-binding-run",
                planner="rule",
                backend="memory",
                preview_fingerprint=preview["plan_identity"]["fingerprint"],
                preview_evidence_fingerprint=binding["fingerprint"],
            )
        finally:
            service.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertTrue(completed["plan_evidence"]["evidence_fingerprint_match"])
        self.assertEqual(
            completed["plan_evidence"]["evidence_binding"],
            binding,
        )

    def test_changed_evidence_blocks_before_tool_dispatch(self):
        service = AgentService(domain_pack=TextDomainPack())
        try:
            rejected = service.run(
                "请总结这段文本",
                session_id="m193-binding-drift",
                planner="rule",
                backend="memory",
                preview_evidence_fingerprint="sha256:stale-preview-evidence",
            )
            interaction = rejected["result"]["selection_interaction"]
            repaired = service.apply_run_interaction(
                rejected["run_id"],
                "repair",
                {},
                planner="rule",
                backend="memory",
            )
        finally:
            service.close()

        self.assertEqual(rejected["status"], "FAILED")
        self.assertEqual(rejected["steps"], [])
        planning = rejected["plan_evidence"]
        self.assertFalse(planning["evidence_fingerprint_match"])
        self.assertEqual(
            planning["evidence_revalidation"]["state"],
            "changed",
        )
        self.assertEqual(rejected["failure"]["code"], "preview_evidence_changed")
        self.assertEqual(interaction["state"], "repairable")
        self.assertIn("repair", interaction["allowed_actions"])
        self.assertIn("preview", interaction["allowed_actions"])
        self.assertEqual(repaired["status"], "PLANNED")

    def test_binding_survives_artifact_async_and_restart(self):
        with tempfile.TemporaryDirectory(prefix="m193-evidence-entry-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
                domain_pack=TextDomainPack(),
            )
            try:
                preview = service.preview(
                    "请总结这段文本",
                    session_id="m193-entry-preview",
                    planner="rule",
                    backend="memory",
                )
                binding = preview["evidence_binding"]
                completed = service.run(
                    "请总结这段文本",
                    session_id="m193-entry-run",
                    planner="rule",
                    backend="memory",
                    preview_fingerprint=preview["plan_identity"]["fingerprint"],
                    preview_evidence_fingerprint=binding["fingerprint"],
                    export_artifact=True,
                )
                detail = service.get_run(completed["run_id"])
                artifact = store.read_run(completed["run_id"], domain_id="text")
                async_evidence = normalize_async_result_evidence(
                    build_async_result_evidence(
                        detail["result"], status=detail["status"]
                    ),
                    status=detail["status"],
                )
            finally:
                service.close()

            restarted = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=ArtifactStore(root / "artifacts"),
                domain_pack=TextDomainPack(),
            )
            try:
                recovered = restarted.get_run(
                    completed["run_id"], planner="rule", backend="memory"
                )
            finally:
                restarted.close()

        self.assertEqual(
            compare_evidence_bindings(
                [completed, detail, artifact, async_evidence, recovered]
            ),
            [],
        )

    def test_http_preview_binding_is_required_by_the_run_gate(self):
        service = AgentService(domain_pack=TextDomainPack())

        class Handler(AgentApiHandler):
            pass

        Handler.service = service
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            preview = _request_json(
                server.server_address,
                "/runs/preview",
                {
                    "request": "请总结这段文本",
                    "session_id": "m193-http-preview",
                    "planner": "rule",
                    "backend": "memory",
                },
            )
            completed = _request_json(
                server.server_address,
                "/runs",
                {
                    "request": "请总结这段文本",
                    "session_id": "m193-http-run",
                    "planner": "rule",
                    "backend": "memory",
                    "preview_fingerprint": preview["plan_identity"]["fingerprint"],
                    "preview_evidence_fingerprint": preview["evidence_binding"][
                        "fingerprint"
                    ],
                },
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            service.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertTrue(completed["plan_evidence"]["evidence_fingerprint_match"])


def _request_json(address, path, payload):
    connection = HTTPConnection(*address, timeout=5)
    try:
        connection.request(
            "POST",
            path,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()
    if response.status >= 400:
        raise AssertionError("HTTP {}: {}".format(response.status, data))
    return data


if __name__ == "__main__":
    unittest.main()
