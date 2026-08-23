"""M227: one canonical interaction contract and authoritative Action Host."""

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.contract_versions import INTERACTION_COMMAND_SCHEMA_VERSION
from agent.domain_routing_entry import DomainRoutingApplication, DomainRoutingState
from agent.domain_selection import DomainSelection
from agent.domain_selector import DomainRouter, DomainRoutingCandidate, DomainRoutingDecision
from agent.interaction_contract import (
    INTERACTION_SCHEMA_VERSION,
    InteractionContractError,
    project_interaction,
    validate_interaction_command,
)
from agent.service import AgentService
from agent.service_async import build_async_result_evidence
from serve_api import AgentApiHandler


class _CatalogHost:
    def catalog(self):
        return {"domain_ids": ["gis", "text"]}


def _ambiguous_decision() -> DomainRoutingDecision:
    request = "空间智能体"
    return DomainRoutingDecision(
        decision_id="m227-routing-root",
        status="ambiguous",
        reason_code="domain_selection_required",
        selector_id="fixture.v1",
        request_fingerprint=hashlib.sha256(request.encode("utf-8")).hexdigest(),
        candidates=(
            DomainRoutingCandidate("gis", "空间分析", score=50),
            DomainRoutingCandidate("text", "文本处理", score=50),
        ),
    )


class M227InteractionContractTests(unittest.TestCase):
    def test_actions_are_the_only_authorization_source_and_commands_are_bounded(self):
        decision = _ambiguous_decision()
        source = {
            "domain_routing": decision.to_dict(),
            "domain_routing_interaction": {
                "schema_version": "spatial-agent.domain-routing-interaction.v1",
                "available": True,
                "state": "candidate_selection",
                "reason_code": "domain_selection_required",
                "decision_id": decision.decision_id,
                "candidates": [item.to_dict() for item in decision.candidates],
                "allowed_actions": ["select_domain"],
                "actions": [{
                    "id": "select_domain",
                    "label": "选择领域",
                    "input_schema": {
                        "type": "object",
                        "properties": {"domain_id": {"type": "string", "enum": ["gis", "text"]}},
                        "required": ["domain_id"],
                        "additionalProperties": False,
                    },
                }],
            },
        }
        interaction = project_interaction(source)
        self.assertEqual(interaction["schema_version"], INTERACTION_SCHEMA_VERSION)
        self.assertEqual(interaction["subject"]["root"]["id"], decision.decision_id)
        self.assertEqual([item["id"] for item in interaction["actions"]], ["select_domain"])

        command = {
            "schema_version": INTERACTION_COMMAND_SCHEMA_VERSION,
            "subject": interaction["subject"],
            "action_id": "select_domain",
            "input": {"domain_id": "gis"},
            "idempotency_key": "m227-select-gis",
        }
        self.assertEqual(
            validate_interaction_command(command, interaction)["input"],
            {"domain_id": "gis"},
        )
        invalid = {**command, "input": {"domain_id": "future-domain"}}
        with self.assertRaises(InteractionContractError) as captured:
            validate_interaction_command(invalid, interaction)
        self.assertEqual(captured.exception.code, "interaction_input_enum")

    def test_routing_override_uses_revision_cas_and_replays_one_child(self):
        state = DomainRoutingState()
        decision = _ambiguous_decision()
        state.save(decision, "m227-routing-session")
        application = DomainRoutingApplication(
            _CatalogHost(),
            router=DomainRouter(enabled_domain_ids=("gis", "text")),
            state=state,
        )

        first = application.override(
            decision.decision_id,
            {"domain_id": "gis", "session_id": "m227-routing-session"},
        )
        replay = application.override(
            decision.decision_id,
            {"domain_id": "gis", "session_id": "m227-routing-session"},
        )
        self.assertEqual(
            first["domain_routing"]["decision_id"],
            replay["domain_routing"]["decision_id"],
        )
        self.assertEqual(first["interaction"]["state"], "completed")
        self.assertEqual(
            first["interaction"]["subject"]["root"]["id"],
            decision.decision_id,
        )
        with self.assertRaises(InteractionContractError) as captured:
            application.override(
                decision.decision_id,
                {"domain_id": "text", "session_id": "m227-routing-session"},
            )
        self.assertEqual(captured.exception.code, "interaction_revision_conflict")

    def test_confirmation_result_async_artifact_and_restart_share_journey(self):
        with tempfile.TemporaryDirectory(prefix="m227-host-") as directory:
            root = Path(directory)
            service = AgentService(
                artifact_store=ArtifactStore(root / "artifacts", legacy_domain_id="text"),
                state_db_path=str(root / "state.db"),
                domain_id="text",
            )
            try:
                waiting = service.run(
                    "请摘要这段文本。",
                    session_id="m227-confirmation",
                    require_confirmation=True,
                    export_artifact=True,
                )
                before = waiting["result"]["interaction"]
                self.assertEqual(before["kind"], "plan_confirmation")
                command = {
                    "schema_version": INTERACTION_COMMAND_SCHEMA_VERSION,
                    "subject": before["subject"],
                    "action_id": "confirm",
                    "input": {},
                    "idempotency_key": "m227-confirm-once",
                }
                completed = service.apply_run_interaction(
                    waiting["run_id"], "", command
                )
                after = completed["result"]["interaction"]
                self.assertEqual(after["state"], "completed")
                self.assertEqual(after["subject"]["root"], before["subject"]["root"])
                self.assertGreater(after["subject"]["revision"], before["subject"]["revision"])
                async_evidence = build_async_result_evidence(
                    completed["result"], status=completed["status"]
                )
                self.assertEqual(async_evidence["interaction"], after)
                artifact = service._artifact_store.read_run(
                    completed["run_id"], domain_id="text"
                )
                self.assertEqual(artifact["result"]["interaction"], after)
            finally:
                service.close()

            restarted = AgentService(
                artifact_store=ArtifactStore(root / "artifacts", legacy_domain_id="text"),
                state_db_path=str(root / "state.db"),
                domain_id="text",
            )
            try:
                recovered = restarted.get_run(waiting["run_id"])
                self.assertEqual(recovered["result"]["interaction"], after)
            finally:
                restarted.close()

    def test_http_rejects_stale_forbidden_and_extra_input_with_stable_codes(self):
        with tempfile.TemporaryDirectory(prefix="m227-http-") as directory:
            root = Path(directory)
            service = AgentService(
                artifact_store=ArtifactStore(root / "artifacts", legacy_domain_id="text"),
                state_db_path=str(root / "state.db"),
                domain_id="text",
            )
            waiting = service.run(
                "请摘要这段文本。",
                session_id="m227-http",
                require_confirmation=True,
            )
            interaction = waiting["result"]["interaction"]

            class TextHandler(AgentApiHandler):
                pass

            TextHandler.service = service
            server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = {
                    "schema_version": INTERACTION_COMMAND_SCHEMA_VERSION,
                    "subject": interaction["subject"],
                    "action_id": "confirm",
                    "input": {},
                    "idempotency_key": "m227-http-contract",
                }
                stale_subject = {
                    **interaction["subject"],
                    "revision": interaction["subject"]["revision"] + 1,
                }
                cases = (
                    ({**base, "subject": stale_subject}, "interaction_revision_conflict"),
                    (
                        {
                            **base,
                            "action_id": "select_domain",
                            "input": {"domain_id": "text"},
                        },
                        "interaction_action_not_allowed",
                    ),
                    (
                        {**base, "input": {"unexpected": True}},
                        "interaction_input_additional_property",
                    ),
                )
                for command, expected_code in cases:
                    status, response = _request_json(
                        server.server_address[1],
                        "/runs/{}/interaction".format(waiting["run_id"]),
                        command,
                    )
                    self.assertEqual(status, 400)
                    self.assertEqual(response["error_code"], expected_code)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()


def _request_json(port: int, path: str, payload: dict) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "POST",
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
