"""M191: selected capabilities can continue with facts without workflow echoing."""

from __future__ import annotations

import unittest
import json
import tempfile
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.domain_contract import DOMAIN_DISCOVERY_SCHEMA_VERSION
from agent.service import AgentService
from domains.text.domain import TextDomainPack
from evaluation.contract_harness import (
    compare_action_transition_evidence,
    compare_action_transition_identities,
)
from serve_api import AgentApiHandler


class FactsRequiredTextDomainPack(TextDomainPack):
    """Domain fixture that pauses before execution until one fact is supplied."""

    def discover(self, request, request_facts):
        del request, request_facts
        return {
            "schema_version": DOMAIN_DISCOVERY_SCHEMA_VERSION,
            "domain_id": self.domain_id,
            "available": True,
            "selected_capability_id": "text_summary",
            "candidate_ids": ["text_summary"],
            "candidate_count": 1,
        }

    def select_workflow(self, discovery, request_facts, *, workflow=None):
        del discovery, request_facts, workflow
        return {
            "source": "domain_discovery",
            "selected_by": "domain",
            "state": "clarification",
            "selected_capability_id": "text_summary",
            "candidate_ids": ["text_summary"],
            "candidate_count": 1,
            "missing_fields": [
                {"id": "text", "label": "文本内容", "kind": "text"}
            ],
        }


class M191SelectionToRunTests(unittest.TestCase):
    def test_provide_facts_resolves_selected_domain_capability_without_workflow(self):
        service = AgentService(domain_pack=FactsRequiredTextDomainPack())
        try:
            pending = service.run(
                request="请处理这段内容",
                session_id="m191-selection-to-run",
                planner="rule",
                backend="memory",
            )
            self.assertEqual(pending["status"], "NEEDS_CLARIFICATION")
            interaction = pending["result"]["selection_interaction"]
            self.assertIn("provide_facts", interaction["allowed_actions"])

            completed = service.apply_run_interaction(
                pending["run_id"],
                "provide_facts",
                {
                    "capability_id": "text_summary",
                    "facts": {"text": "用户输入文本"},
                    "require_confirmation": False,
                },
                planner="rule",
                backend="memory",
            )
        finally:
            service.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(
            completed["result"]["planning"]["workflow_selection"]["selected_capability_id"],
            "text_summary",
        )
        self.assertEqual(completed["result"]["type"], "text_summary_result")

    def test_http_artifact_and_restart_reuse_the_same_selection_to_run_contract(self):
        with tempfile.TemporaryDirectory(prefix="m191-selection-entry-") as directory:
            root = Path(directory)
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=ArtifactStore(root / "artifacts"),
                domain_pack=FactsRequiredTextDomainPack(),
            )
            try:
                pending = service.run(
                    request="请处理这段内容",
                    session_id="m191-selection-http",
                    planner="rule",
                    backend="memory",
                )

                handler_service = service

                class Handler(AgentApiHandler):
                    service = handler_service
                    artifact_root = root / "artifacts"

                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    connection = HTTPConnection(*server.server_address, timeout=5)
                    body = json.dumps(
                        {
                            "action": "provide_facts",
                            "capability_id": "text_summary",
                            "facts": {"source": "HTTP 用户输入"},
                            "require_confirmation": False,
                            "planner": "rule",
                            "backend": "memory",
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")
                    connection.request(
                        "POST",
                        "/runs/{}/interaction".format(pending["run_id"]),
                        body=body,
                        headers={"Content-Type": "application/json"},
                    )
                    response = connection.getresponse()
                    completed = json.loads(response.read().decode("utf-8"))
                    connection.close()
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

                self.assertEqual(response.status, 200)
                artifact = json.loads(
                    Path(completed["artifact_ref"]).read_text(encoding="utf-8")
                )
                history = next(
                    item
                    for item in service.list_runs()["runs"]
                    if item["run_id"] == completed["run_id"]
                )
            finally:
                service.close()

            restarted = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=ArtifactStore(root / "artifacts"),
                domain_pack=FactsRequiredTextDomainPack(),
            )
            try:
                recovered = restarted.get_run(
                    completed["run_id"], planner="rule", backend="memory"
                )
            finally:
                restarted.close()

        self.assertEqual(
            compare_action_transition_identities(
                [completed, artifact, history, recovered]
            ),
            [],
        )
        self.assertEqual(
            compare_action_transition_evidence(
                [completed, artifact, history, recovered]
            ),
            [],
        )
        for payload in (completed, artifact, recovered):
            self.assertEqual(payload["status"], "COMPLETED")
            self.assertEqual(payload["result"]["type"], "text_summary_result")
            self.assertEqual(
                payload["result"]["planning"]["workflow_selection"][
                    "selected_capability_id"
                ],
                "text_summary",
            )
        self.assertTrue(
            completed["action_receipt"]["transition_identity"]["available"]
        )
        self.assertIn("transition_evidence", completed["action_receipt"])


if __name__ == "__main__":
    unittest.main()
