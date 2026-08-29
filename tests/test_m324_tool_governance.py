"""Compact M324 restart rehydration and governance projection checks."""

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from agent.runtime import AgentRuntime
from agent.tooling import (
    InMemoryToolApprovalStore,
    SQLiteToolApprovalStore,
    ToolApprovalRecord,
    project_tool_approval_visibility,
)
from agent.tools import ToolRegistry
from agent.application.http import HTTPApplication
from agent.service import AgentService


def _receipt() -> dict:
    return {
        "schema_version": "spatial-agent.tool-proposal-receipt.v1",
        "proposal_id": "proposal-m324-metric",
        "name": "m324_metric",
        "status": "validated",
        "source_hash": "sha256:m324-source",
        "schema_hash": "sha256:m324-schema",
        "checks": {"normalization": "passed", "sandbox": "passed"},
        "sandbox_profile": {"name": "python-pure-v1", "network": "none"},
        "definition": {
            "name": "m324_metric",
            "description": "计算受控指标",
            "input_schema": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "integer"}},
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "additionalProperties": False,
            },
        },
        "source": "must never cross the approval boundary",
        "example_arguments": {"value": 1},
    }


def _approved(store: InMemoryToolApprovalStore):
    pending = store.create_from_receipt(_receipt(), domain_id="gis")
    return store.resolve(
        pending.approval_id,
        action="approve",
        domain_id="gis",
        expected_version=pending.version,
        expected_fingerprint=pending.receipt_fingerprint,
    )


def _registry() -> ToolRegistry:
    return ToolRegistry(
        {"existing": {"name": "existing", "input_schema": {"type": "object"}}},
        lambda _name, _arguments: {},
    )


class _Validator:
    def __init__(self, available: bool = True):
        self.available = available
        self.calls = []

    def handler_for(self, approval):
        self.calls.append(dict(approval))
        if not self.available:
            return None

        def invoke(arguments):
            return {"value": int(arguments["value"]) + 1}

        return invoke


def _runtime(store, validator, registry=None):
    return AgentRuntime(
        object(),
        registry or _registry(),
        approval_store=store,
        proposal_validator=validator,
        domain_pack=type("Domain", (), {"domain_id": "gis"})(),
    )


class M324ToolGovernanceTests(unittest.TestCase):
    def test_runtime_rehydrates_approved_binding_before_policy_snapshot(self):
        store = InMemoryToolApprovalStore()
        approved = _approved(store)
        validator = _Validator()
        runtime = _runtime(store, validator)

        evidence = runtime.approval_rehydration()
        self.assertEqual(evidence["state"], "ready")
        self.assertEqual(evidence["bound_count"], 1)
        self.assertIn("m324_metric", runtime._execution_policy_resolver.known_tools)
        self.assertEqual(runtime._registry.invoke("m324_metric", {"value": 4}), {"value": 5})
        self.assertEqual(validator.calls[0]["approval_id"], approved.approval_id)
        self.assertNotIn("source", validator.calls[0])

    def test_unavailable_handler_is_degraded_and_not_registered(self):
        store = InMemoryToolApprovalStore()
        _approved(store)
        runtime = _runtime(store, _Validator(available=False))

        evidence = runtime.approval_rehydration()
        self.assertEqual(evidence["state"], "degraded")
        self.assertEqual(evidence["degraded_count"], 1)
        self.assertEqual(evidence["degraded"][0]["reason_code"], "handler_unavailable")
        with self.assertRaisesRegex(Exception, "Unknown tool"):
            runtime._registry.invoke("m324_metric", {"value": 1})

    def test_sqlite_approved_record_rehydrates_after_store_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "m324.db")
            first_store = SQLiteToolApprovalStore(path)
            approved = _approved(first_store)
            restarted_store = SQLiteToolApprovalStore(path)
            runtime = _runtime(restarted_store, _Validator())

            self.assertEqual(runtime.approval_rehydration()["bound_count"], 1)
            self.assertEqual(
                runtime._registry.invoke("m324_metric", {"value": 8}), {"value": 9}
            )
            self.assertEqual(
                runtime.approval_rehydration()["bindings"][0]["approval_id"],
                approved.approval_id,
            )

    def test_repeated_runtime_creation_is_idempotent_and_stale_binding_is_rejected(self):
        store = InMemoryToolApprovalStore()
        approved = _approved(store)
        first = _runtime(store, _Validator())
        second = _runtime(store, _Validator())
        self.assertEqual(first.approval_rehydration()["bound_count"], 1)
        self.assertEqual(second.approval_rehydration()["bound_count"], 1)

        stale = approved.as_dict()
        stale["version"] = approved.version + 1
        with self.assertRaisesRegex(Exception, "stale"):
            first._registry.register_approved_tool(stale, lambda _arguments: {})

    def test_visibility_projection_omits_private_fields_and_reports_recovery(self):
        store = InMemoryToolApprovalStore()
        record = ToolApprovalRecord.from_receipt(_receipt(), domain_id="gis")
        public = project_tool_approval_visibility(record)

        self.assertEqual(public["schema_version"], "spatial-agent.tool-approval-visibility.v1")
        self.assertEqual(public["status"], "pending")
        self.assertEqual(public["recovery"]["state"], "not_loaded")
        self.assertNotIn("definition", public)
        self.assertNotIn("source", public)
        self.assertNotIn("example_arguments", public)
        self.assertEqual(
            store.create_from_receipt(_receipt(), domain_id="gis").approval_id,
            record.approval_id,
        )

    def test_http_application_exposes_safe_visibility_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "http.db"))
            try:
                record = service._state.tool_approval_store.create_from_receipt(
                    _receipt(), domain_id=service._approval_domain_id()
                )
                payload = HTTPApplication(service).read("tool_approvals", {"limit": 8})
                self.assertEqual(payload["count"], 1)
                visible = payload["visibility"][0]
                self.assertEqual(visible["approval_id"], record.approval_id)
                self.assertEqual(visible["recovery"]["state"], "not_loaded")
                self.assertNotIn("definition", visible)
                self.assertNotIn("source", visible)
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
