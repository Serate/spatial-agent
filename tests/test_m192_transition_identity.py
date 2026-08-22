"""M192-A: source-to-result transition identity is versioned and bounded."""

from __future__ import annotations

import unittest

from agent.action_identity import (
    ACTION_TRANSITION_IDENTITY_SCHEMA_VERSION,
    build_action_transition_identity,
    normalize_action_transition_identity,
)
from agent.recovery_action import project_action_receipt


def _run_payload(request: str, plan: str, result_type: str) -> dict:
    return {
        "request": request,
        "resolved_request": request,
        "status": "COMPLETED",
        "result_type": result_type,
        "plan_evidence": {
            "plan_identity": {
                "version": "spatial-agent.plan-identity.v1",
                "fingerprint": "sha256:" + plan,
            }
        },
        "result": {
            "schema_version": "spatial-agent.result-envelope.v1",
            "type": result_type,
            "request_identity": {
                "schema_version": "spatial-agent.request-identity.v1",
                "fingerprint": "sha256:" + request.encode("utf-8").hex()[:64].ljust(64, "0"),
            },
            "planning": {
                "plan_identity": {
                    "version": "spatial-agent.plan-identity.v1",
                    "fingerprint": "sha256:" + plan,
                }
            },
        },
    }


class M192TransitionIdentityTests(unittest.TestCase):
    def test_projection_binds_source_and_result_without_transport_ids(self):
        source = _run_payload("请处理一段内容", "source", "clarification")
        target = _run_payload("请处理一段内容", "target", "text_summary_result")
        transition = build_action_transition_identity(source, target)
        receipt = project_action_receipt(
            {
                "action": "provide_facts",
                "status": "COMPLETED",
                "run_id": "source-run-id",
                "result_run_id": "target-run-id",
                "transition_identity": transition,
            }
        )
        normalized = normalize_action_transition_identity(
            receipt["transition_identity"]
        )

        self.assertEqual(
            normalized["schema_version"],
            ACTION_TRANSITION_IDENTITY_SCHEMA_VERSION,
        )
        self.assertTrue(normalized["available"])
        self.assertNotIn("source-run-id", str(normalized))
        self.assertNotIn("target-run-id", str(normalized))
        self.assertEqual(
            normalized["source"]["plan_identity"]["fingerprint"],
            "sha256:source",
        )
        self.assertEqual(
            normalized["result"]["plan_identity"]["fingerprint"],
            "sha256:target",
        )

    def test_unknown_transition_schema_degrades_to_unavailable(self):
        self.assertIsNone(
            normalize_action_transition_identity(
                {"schema_version": "spatial-agent.action-transition-identity.v9"}
            )
        )


if __name__ == "__main__":
    unittest.main()
