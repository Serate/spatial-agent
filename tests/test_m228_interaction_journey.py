"""M228: one persisted interaction journey crosses Application and transports."""

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.contract_versions import INTERACTION_COMMAND_SCHEMA_VERSION
from agent.domain_routing_entry import DomainRoutingApplication, DomainRoutingState
from agent.domain_selector import (
    DomainRouter,
    DomainRoutingCandidate,
    DomainRoutingDecision,
)
from agent.service import AgentService
from agent.sqlite_store import SQLiteConversationStore
from evaluation.interaction_journey_harness import (
    capture_interaction_journey,
    compare_interaction_entries,
)
from serve_api import AgentApiHandler


class _AmbiguousRouter:
    def __init__(self, root_id: str = "m228-routing-root") -> None:
        self._router = DomainRouter(enabled_domain_ids=("gis", "text"))
        self._root_id = root_id

    def catalog(self):
        return self._router.catalog()

    def route(self, request, *, domain_id=None):
        if request == "需要选择处理领域":
            return DomainRoutingDecision(
                decision_id=self._root_id,
                status="ambiguous",
                reason_code="domain_selection_required",
                selector_id="m228.fixture",
                request_fingerprint=hashlib.sha256(request.encode()).hexdigest(),
                candidates=(
                    DomainRoutingCandidate("gis", "空间分析", score=50),
                    DomainRoutingCandidate("text", "文本处理", score=50),
                ),
            )
        return self._router.route(request, domain_id=domain_id)

    def restore(self, request, domain_id, *, parent_decision_id=None):
        return self._router.restore(
            request,
            domain_id,
            parent_decision_id=parent_decision_id,
        )

    def override(self, prior, domain_id):
        return self._router.override(prior, domain_id)

    def resolve(self, decision):
        return self._router.resolve(decision)


class _Host:
    def __init__(self, service: AgentService) -> None:
        self._service = service

    def catalog(self):
        return {"domain_ids": ["gis", "text"]}

    def service(self, selection):
        domain_id = getattr(selection, "domain_id", selection)
        if domain_id != "text":
            raise ValueError("fixture only executes the selected text Domain")
        return self._service


class M228InteractionJourneyTests(unittest.TestCase):
    def test_application_http_artifact_and_restart_share_one_journey(self):
        with tempfile.TemporaryDirectory(prefix="m228-journey-") as directory:
            root = Path(directory)
            database = str(root / "state.db")
            artifacts = root / "artifacts"
            service = AgentService(
                state_db_path=database,
                artifact_store=ArtifactStore(artifacts, legacy_domain_id="text"),
                domain_id="text",
            )
            host = _Host(service)
            router = _AmbiguousRouter()
            application = DomainRoutingApplication(
                host,
                router=router,
                state=DomainRoutingState(SQLiteConversationStore(database)),
            )
            ambiguous = application.select(
                {
                    "request": "需要选择处理领域",
                    "session_id": "m228-session",
                }
            )
            command = {
                "schema_version": INTERACTION_COMMAND_SCHEMA_VERSION,
                "subject": ambiguous["interaction"]["subject"],
                "action_id": "select_domain",
                "input": {"domain_id": "text"},
                "idempotency_key": "m228-select-text",
                "session_id": "m228-session",
            }

            class Handler(AgentApiHandler):
                pass

            Handler.service = service
            Handler.host = host
            Handler.routing = application
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, selected = _request_json(
                    server.server_address[1],
                    "POST",
                    "/domain-routing/decisions/m228-routing-root/select",
                    command,
                )
                self.assertEqual(status, 200)
                self.assertEqual(selected["action_receipt"]["status"], "COMPLETED")
                self.assertEqual(
                    selected["action_receipt"]["subject"]["kind"],
                    "routing_decision",
                )

                restarted_application = DomainRoutingApplication(
                    host,
                    router=_AmbiguousRouter(),
                    state=DomainRoutingState(SQLiteConversationStore(database)),
                )
                replay = restarted_application.override(
                    "m228-routing-root",
                    command,
                )
                self.assertTrue(replay["action_receipt"]["reused"])
                self.assertEqual(compare_interaction_entries([selected, replay]), [])
                Handler.routing = restarted_application

                selected_decision_id = selected["domain_routing"]["decision_id"]
                status, waiting = _request_json(
                    server.server_address[1],
                    "POST",
                    "/runs/auto",
                    {
                        "request": "请摘要这段文本。",
                        "session_id": "m228-session",
                        "domain_routing_decision_id": selected_decision_id,
                        "require_confirmation": True,
                        "export_artifact": True,
                    },
                )
                self.assertEqual(status, 200)
                self.assertEqual(
                    waiting["result"]["interaction"]["state"],
                    "confirmation_required",
                )
                confirmation = waiting["result"]["interaction"]
                status, completed = _request_json(
                    server.server_address[1],
                    "POST",
                    "/runs/{}/interaction".format(waiting["run_id"]),
                    {
                        "schema_version": INTERACTION_COMMAND_SCHEMA_VERSION,
                        "subject": confirmation["subject"],
                        "action_id": "confirm",
                        "input": {},
                        "idempotency_key": "m228-confirm",
                    },
                )
                self.assertEqual(status, 200)
                journey = capture_interaction_journey(
                    [ambiguous, selected, waiting, completed]
                )
                self.assertTrue(journey["valid"], journey["reason_codes"])
                self.assertEqual(
                    [item["state"] for item in journey["events"]],
                    [
                        "candidate_selection",
                        "completed",
                        "confirmation_required",
                        "completed",
                    ],
                )
                artifact = service._artifact_store.read_run(
                    completed["run_id"],
                    domain_id="text",
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

            restarted_service = AgentService(
                state_db_path=database,
                artifact_store=ArtifactStore(artifacts, legacy_domain_id="text"),
                domain_id="text",
            )
            try:
                recovered = restarted_service.get_run(completed["run_id"])
                self.assertEqual(
                    compare_interaction_entries([completed, artifact, recovered]),
                    [],
                )
            finally:
                restarted_service.close()
            self._assert_atomic_multi_store_replay(database, host)

    def _assert_atomic_multi_store_replay(self, database: str, host: _Host) -> None:
        root_id = "m228-concurrent-root"
        seed = DomainRoutingApplication(
            host,
            router=_AmbiguousRouter(root_id),
            state=DomainRoutingState(SQLiteConversationStore(database)),
        )
        initial = seed.select(
            {
                "request": "需要选择处理领域",
                "session_id": "m228-concurrent-session",
            }
        )
        command = {
            "schema_version": INTERACTION_COMMAND_SCHEMA_VERSION,
            "subject": initial["interaction"]["subject"],
            "action_id": "select_domain",
            "input": {"domain_id": "text"},
            "idempotency_key": "m228-concurrent-select",
            "session_id": "m228-concurrent-session",
        }
        applications = [
            DomainRoutingApplication(
                host,
                router=_AmbiguousRouter(root_id),
                state=DomainRoutingState(SQLiteConversationStore(database)),
            )
            for _ in range(2)
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda application: application.override(root_id, command),
                    applications,
                )
            )
        self.assertEqual(
            len({item["domain_routing"]["decision_id"] for item in results}),
            1,
        )
        self.assertEqual(
            sorted(item["action_receipt"]["reused"] for item in results),
            [False, True],
        )


def _request_json(port: int, method: str, path: str, payload: dict) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(
            method,
            path,
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
