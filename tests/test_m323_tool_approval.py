"""Compact M323 approval contracts and persistence checks."""

from __future__ import annotations

import tempfile
import unittest
import os
import json
import threading
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.tooling import (
    InMemoryToolApprovalStore,
    SQLiteToolApprovalStore,
    ToolApprovalError,
    ToolApprovalRecord,
    ToolProposalValidator,
    UnixSocketSandboxClient,
)
from agent.tools import ToolRegistry
from agent.application.http import HTTPApplication
from agent.service import AgentService
from serve_api import AgentApiHandler


def _receipt(*, status: str = "validated") -> dict:
    return {
        "schema_version": "spatial-agent.tool-proposal-receipt.v1",
        "proposal_id": "proposal-safe-metric",
        "name": "safe_metric",
        "status": status,
        "source_hash": "sha256:source",
        "schema_hash": "sha256:schema",
        "checks": {"normalization": "passed", "sandbox": "passed"},
        "sandbox_profile": {"name": "python-pure-v1", "network": "none"},
        "definition": {
            "name": "safe_metric",
            "description": "计算一个指标",
            "input_schema": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "integer"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
            },
        },
        "source": "must never be copied",
        "example_arguments": {"value": 1},
    }


class M323ApprovalContractTests(unittest.TestCase):
    def test_valid_receipt_creates_bounded_pending_record(self):
        record = ToolApprovalRecord.from_receipt(
            _receipt(), domain_id="gis", expires_at=2_000.0, now=1_000.0
        )
        public = record.as_dict()
        self.assertEqual(record.status, "pending")
        self.assertEqual(record.version, 1)
        self.assertTrue(record.approval_id.startswith("approval-"))
        self.assertTrue(record.receipt_fingerprint.startswith("sha256:"))
        self.assertEqual(public["allowed_actions"], ["approve", "reject"])
        self.assertNotIn("source", public)
        self.assertNotIn("example_arguments", public)
        self.assertEqual(public["definition"]["name"], "safe_metric")

    def test_state_matrix_idempotency_and_revoke(self):
        store = InMemoryToolApprovalStore()
        record = store.create_from_receipt(_receipt(), domain_id="gis")
        approved = store.resolve(
            record.approval_id,
            action="approve",
            domain_id="gis",
            expected_version=1,
            expected_fingerprint=record.receipt_fingerprint,
            actor_id="reviewer-1",
        )
        self.assertEqual(approved.status, "approved")
        self.assertEqual(approved.version, 2)
        repeated = store.resolve(
            record.approval_id,
            action="approve",
            domain_id="gis",
            expected_fingerprint=record.receipt_fingerprint,
        )
        self.assertEqual(repeated, approved)
        revoked = store.resolve(
            record.approval_id,
            action="revoke",
            domain_id="gis",
            expected_version=2,
            expected_fingerprint=record.receipt_fingerprint,
        )
        self.assertEqual(revoked.status, "revoked")
        self.assertEqual([item["to_status"] for item in revoked.decision_receipts], ["approved", "revoked"])

    def test_rejects_stale_or_missing_preconditions_and_invalid_receipts(self):
        store = InMemoryToolApprovalStore()
        record = store.create_from_receipt(_receipt(), domain_id="gis")
        with self.assertRaisesRegex(ToolApprovalError, "precondition"):
            store.resolve(record.approval_id, action="approve", domain_id="gis")
        with self.assertRaisesRegex(ToolApprovalError, "version mismatch"):
            store.resolve(record.approval_id, action="approve", domain_id="gis", expected_version=9)
        with self.assertRaisesRegex(ToolApprovalError, "fingerprint mismatch"):
            store.resolve(
                record.approval_id,
                action="approve",
                domain_id="gis",
                expected_fingerprint="sha256:wrong",
            )
        invalid = store.create_from_receipt(_receipt(status="unavailable"), domain_id="gis")
        self.assertEqual(invalid.status, "invalid")
        self.assertEqual(invalid.allowed_actions(), ())

    def test_expiration_is_a_persisted_transition(self):
        record = ToolApprovalRecord.from_receipt(
            _receipt(), domain_id="gis", expires_at=10.0, now=1.0
        )
        expired = record.expire(now=10.0)
        self.assertEqual(expired.status, "expired")
        self.assertEqual(expired.version, 2)
        self.assertEqual(expired.decision_receipts[-1]["action"], "expire")
        with self.assertRaisesRegex(ToolApprovalError, "not allowed"):
            expired.transition(
                "approve",
                expected_fingerprint=expired.receipt_fingerprint,
                now=10.0,
            )

    def test_sqlite_record_survives_restart_without_private_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            first = SQLiteToolApprovalStore(path)
            record = first.create_from_receipt(_receipt(), domain_id="gis")
            approved = first.resolve(
                record.approval_id,
                action="approve",
                domain_id="gis",
                expected_version=1,
                expected_fingerprint=record.receipt_fingerprint,
            )
            second = SQLiteToolApprovalStore(path)
            restored = second.get(record.approval_id, domain_id="gis")
            self.assertIsNotNone(restored)
            self.assertEqual(restored.status, "approved")
            self.assertEqual(restored.version, approved.version)
            self.assertEqual(restored.as_dict()["definition"]["name"], "safe_metric")
            self.assertNotIn("source", restored.as_dict())
            self.assertNotIn("example_arguments", restored.as_dict())

    def test_sqlite_expired_record_is_listable_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "expired.db")
            first = SQLiteToolApprovalStore(path)
            record = first.create_from_receipt(
                _receipt(), domain_id="gis", expires_at=time.time() - 1
            )
            second = SQLiteToolApprovalStore(path)
            expired = second.list(domain_id="gis", status="expired")
            self.assertEqual([item.approval_id for item in expired], [record.approval_id])
            self.assertEqual(expired[0].status, "expired")

    def test_registry_accepts_only_approved_record_and_can_revoke_binding(self):
        store = InMemoryToolApprovalStore()
        pending = store.create_from_receipt(_receipt(), domain_id="gis")
        registry = ToolRegistry(
            {"existing": {"name": "existing", "input_schema": {"type": "object"}}},
            lambda name, arguments: {},
        )
        with self.assertRaisesRegex(Exception, "approved"):
            registry.register_approved_tool(pending.as_dict(), lambda arguments: {})
        approved = store.resolve(
            pending.approval_id,
            action="approve",
            domain_id="gis",
            expected_version=1,
            expected_fingerprint=pending.receipt_fingerprint,
        )
        registered = registry.register_approved_tool(
            approved.as_dict(), lambda arguments: {"value": arguments["value"]}
        )
        self.assertEqual(registered["approval_id"], approved.approval_id)
        self.assertEqual(registry.invoke("safe_metric", {"value": 4}), {"value": 4})
        self.assertTrue(registry.revoke_approved_tool(approved.approval_id))
        with self.assertRaisesRegex(Exception, "Unknown tool"):
            registry.invoke("safe_metric", {"value": 4})

    def test_runtime_approval_guard_blocks_revoked_old_binding(self):
        store = InMemoryToolApprovalStore()
        pending = store.create_from_receipt(_receipt(), domain_id="gis")
        approved = store.resolve(
            pending.approval_id,
            action="approve",
            domain_id="gis",
            expected_version=1,
            expected_fingerprint=pending.receipt_fingerprint,
        )
        registry = ToolRegistry(
            {"existing": {"name": "existing", "input_schema": {"type": "object"}}},
            lambda name, arguments: {},
        )
        registry.register_approved_tool(
            approved.as_dict(), lambda arguments: {"value": arguments["value"]}
        )
        from agent.runtime import AgentRuntime

        runtime = AgentRuntime(
            object(),
            registry,
            approval_store=store,
            domain_pack=type("Domain", (), {"domain_id": "gis"})(),
        )
        self.assertEqual(registry.invoke("safe_metric", {"value": 4}), {"value": 4})
        store.resolve(
            approved.approval_id,
            action="revoke",
            domain_id="gis",
            expected_version=approved.version,
            expected_fingerprint=approved.receipt_fingerprint,
        )
        with self.assertRaisesRegex(Exception, "失效"):
            registry.invoke("safe_metric", {"value": 4})
        runtime._conversation_store.clear_pending("default")

    def test_http_semantic_approval_survives_service_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            service = AgentService(state_db_path=path)
            try:
                domain_id = service._approval_domain_id()
                record = service._state.tool_approval_store.create_from_receipt(
                    _receipt(), domain_id=domain_id
                )
                http = HTTPApplication(service)
                listing = http.read("tool_approvals", {"limit": 10})
                self.assertEqual(listing["count"], 1)
                approved = http.execute(
                    "tool_approval_resolve",
                    {
                        "action": "approve",
                        "expected_version": 1,
                        "receipt_fingerprint": record.receipt_fingerprint,
                        "actor_id": "reviewer-1",
                    },
                    run_id=record.approval_id,
                )
                self.assertEqual(approved["approval"]["status"], "approved")
                self.assertEqual(approved["registration_count"], 0)
            finally:
                service.close()
            restarted = AgentService(state_db_path=path)
            try:
                restored = HTTPApplication(restarted).read(
                    "tool_approval", resource_id=record.approval_id
                )["approval"]
                self.assertEqual(restored["status"], "approved")
                revoked = HTTPApplication(restarted).execute(
                    "tool_approval_resolve",
                    {
                        "action": "revoke",
                        "expected_version": restored["version"],
                        "receipt_fingerprint": restored["receipt_fingerprint"],
                    },
                    run_id=record.approval_id,
                )
                self.assertEqual(revoked["approval"]["status"], "revoked")
            finally:
                restarted.close()

    @unittest.skipUnless(os.name == "posix", "sandbox worker uses Unix sockets")
    def test_validated_sandbox_proposal_can_be_published_after_approval(self):
        proposal = {
            "name": "live_metric",
            "description": "执行一个受控指标计算",
            "input_schema": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "integer"}},
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "integer"}},
                "additionalProperties": False,
            },
            "source": 'def run(arguments):\n    return {"value": arguments["value"] + 1}\n',
            "example_arguments": {"value": 1},
        }
        client = UnixSocketSandboxClient("/app/outputs/sandbox/worker.sock")
        validator = ToolProposalValidator(client)
        receipt = validator.validate(proposal)
        if receipt.get("status") != "validated":
            self.skipTest("sandbox sidecar is unavailable: " + str(receipt.get("reason_code")))
        store = InMemoryToolApprovalStore()
        pending = store.create_from_receipt(receipt, domain_id="gis")
        approved = store.resolve(
            pending.approval_id,
            action="approve",
            domain_id="gis",
            expected_version=1,
            expected_fingerprint=pending.receipt_fingerprint,
        )
        registry = ToolRegistry(
            {"existing": {"name": "existing", "input_schema": {"type": "object"}}},
            lambda name, arguments: {},
        )
        registry.register_approved_tool(approved.as_dict(), validator.handler_for(approved.as_dict()))
        self.assertEqual(registry.invoke("live_metric", {"value": 4}), {"value": 5})

    def test_stdlib_http_exposes_same_approval_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            state_db_path = str(Path(directory) / "stdlib-http.db")
            service = AgentService(state_db_path=state_db_path)
            class TestHandler(AgentApiHandler):
                pass
            TestHandler.service = service
            try:
                record = service._state.tool_approval_store.create_from_receipt(
                    _receipt(), domain_id=service._approval_domain_id()
                )
                server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                    try:
                        connection.request("GET", "/tools/approvals/" + record.approval_id)
                        response = connection.getresponse()
                        self.assertEqual(response.status, 200)
                        detail = json.loads(response.read().decode("utf-8"))
                        self.assertEqual(detail["approval"]["status"], "pending")
                        connection.request(
                            "POST",
                            "/tools/approvals/" + record.approval_id + "/resolve",
                            body=json.dumps({
                                "action": "reject",
                                "expected_version": 1,
                                "receipt_fingerprint": record.receipt_fingerprint,
                            }),
                            headers={"Content-Type": "application/json"},
                        )
                        response = connection.getresponse()
                        self.assertEqual(response.status, 200)
                        resolved = json.loads(response.read().decode("utf-8"))
                        self.assertEqual(resolved["approval"]["status"], "rejected")
                    finally:
                        connection.close()
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
