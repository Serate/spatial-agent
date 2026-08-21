"""M151: decision lifecycle contract and optimistic concurrency seam."""

import unittest
import tempfile
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from agent.service import AgentService
from serve_api import AgentApiHandler
from agent.decision_lifecycle import (
    DECISION_LIFECYCLE_SCHEMA_VERSION,
    DecisionLifecycleError,
    DecisionRequest,
    InMemoryDecisionStore,
    SQLiteDecisionStore,
    build_decision_evidence,
    transition_decision,
)


def _request(**changes):
    value = {
        "subject_kind": "run",
        "subject_id": "run-m151",
        "domain_id": "text",
        "session_id": "m151",
        "decision_kind": "plan_confirmation",
        "prompt": "是否执行当前计划？",
        "options": ("approve", "reject"),
        "subject_fingerprint": "sha256:plan-m151",
    }
    value.update(changes)
    return DecisionRequest(**value)


class M151DecisionLifecycleTests(unittest.TestCase):
    def test_http_decision_route_covers_wait_get_and_resolve(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            pending = _request_json(
                port,
                "POST",
                "/runs",
                {
                    "request": "查询DEM栅格元数据",
                    "session_id": "m151-http",
                    "require_confirmation": True,
                },
            )
            evidence = pending["decision_evidence"]
            decision = _request_json(port, "GET", "/decisions/" + evidence["decision_id"])
            self.assertEqual(decision["decision"]["status"], "PENDING")
            completed = _request_json(
                port,
                "POST",
                "/decisions/" + evidence["decision_id"] + "/resolve",
                {"choice": "approve", "expected_version": evidence["version"]},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(completed["status"], "COMPLETED")

    def test_service_pauses_then_resumes_the_persisted_plan(self):
        service = AgentService()
        waiting = service.run(
            "查询DEM栅格元数据",
            session_id="m151-service",
            require_confirmation=True,
        )
        self.assertEqual(waiting["status"], "WAITING_FOR_DECISION")
        evidence = waiting["decision_evidence"]
        self.assertEqual(evidence["state"], "awaiting_confirmation")
        decision_id = evidence["decision_id"]
        self.assertEqual(service.get_decision(decision_id)["evidence"]["version"], 1)

        completed = service.resolve_decision(
            decision_id,
            "approve",
            expected_version=evidence["version"],
        )
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["decision_evidence"]["state"], "completed")
        self.assertEqual(completed["result"]["type"], "raster_metadata_result")

    def test_rejection_does_not_dispatch_waiting_plan(self):
        service = AgentService()
        waiting = service.run(
            "查询DEM栅格元数据",
            session_id="m151-reject",
            require_confirmation=True,
        )
        evidence = waiting["decision_evidence"]
        rejected = service.resolve_decision(
            evidence["decision_id"],
            "reject",
            expected_version=evidence["version"],
        )
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertEqual(rejected["decision_evidence"]["state"], "rejected")
        self.assertTrue(all(step["status"] == "PENDING" for step in rejected["steps"]))

    def test_sqlite_decision_and_waiting_run_survive_service_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = directory + "/state.db"
            first = AgentService(state_db_path=path)
            waiting = first.run(
                "查询DEM栅格元数据",
                session_id="m151-reopen",
                require_confirmation=True,
            )
            evidence = waiting["decision_evidence"]
            second = AgentService(state_db_path=path)
            self.assertEqual(
                second.get_decision(evidence["decision_id"])["decision"]["status"],
                "PENDING",
            )
            completed = second.resolve_decision(
                evidence["decision_id"],
                "approve",
                expected_version=evidence["version"],
            )
            self.assertEqual(completed["status"], "COMPLETED")

    def test_pending_decision_can_be_resolved_and_consumed_once(self):
        store = InMemoryDecisionStore()
        record = store.create(_request())
        self.assertEqual(record.status, "PENDING")
        self.assertEqual(record.evidence()["state"], "awaiting_confirmation")

        accepted = store.resolve(
            record.decision_id,
            domain_id="text",
            choice="accept",
            expected_version=1,
        )
        self.assertEqual(accepted.status, "ACCEPTED")
        consumed = store.consume(
            record.decision_id,
            domain_id="text",
            expected_version=accepted.version,
        )
        self.assertEqual(consumed.status, "CONSUMED")
        self.assertEqual(consumed.evidence()["state"], "completed")

        with self.assertRaises(DecisionLifecycleError) as error:
            store.resolve(record.decision_id, domain_id="text", choice="approve")
        self.assertEqual(error.exception.code, "decision_not_pending")

    def test_wrong_domain_and_stale_version_are_rejected(self):
        store = InMemoryDecisionStore()
        record = store.create(_request())
        self.assertIsNone(store.get(record.decision_id, domain_id="gis"))
        with self.assertRaises(DecisionLifecycleError) as error:
            store.resolve(
                record.decision_id,
                domain_id="text",
                choice="approve",
                expected_version=9,
            )
        self.assertEqual(error.exception.code, "decision_version_mismatch")

    def test_projection_and_transition_are_versioned_and_bounded(self):
        evidence = build_decision_evidence(
            "awaiting_confirmation",
            allowed_actions=("approve", "reject"),
            plan_fingerprint="sha256:plan",
        )
        self.assertEqual(
            evidence["schema_version"], DECISION_LIFECYCLE_SCHEMA_VERSION
        )
        approved = transition_decision(evidence, "approve")
        self.assertEqual(approved["state"], "approved")
        self.assertEqual(approved["plan_fingerprint"], "sha256:plan")
        with self.assertRaises(DecisionLifecycleError) as error:
            transition_decision(approved, "approve")
        self.assertEqual(error.exception.code, "decision_action_not_allowed")

    def test_sqlite_store_survives_reopen_and_keeps_domain_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = directory + "/state.db"
            first = SQLiteDecisionStore(path)
            record = first.create(_request())
            resolved = first.resolve(
                record.decision_id,
                domain_id="text",
                choice="approve",
                expected_version=1,
            )
            reopened = SQLiteDecisionStore(path)
            loaded = reopened.get(record.decision_id, domain_id="text")
            self.assertEqual(loaded.status, "ACCEPTED")
            self.assertEqual(loaded.version, resolved.version)
            self.assertIsNone(reopened.get(record.decision_id, domain_id="gis"))


def _request_json(port, method, path, payload=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = json.loads(response.read().decode("utf-8"))
    connection.close()
    if response.status >= 400:
        raise AssertionError("HTTP {}: {}".format(response.status, data))
    return data


if __name__ == "__main__":
    unittest.main()
