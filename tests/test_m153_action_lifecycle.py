"""M153: one bounded lifecycle projection across result and async seams."""

import unittest

from agent.action_lifecycle import (
    ACTION_LIFECYCLE_SCHEMA_VERSION,
    project_action_lifecycle,
)
from agent.service_async import (
    build_async_result_evidence,
    normalize_async_result_evidence,
)
from result_contract import build_result_contract
from evaluation.contract_harness import compare_results


class M153ActionLifecycleTests(unittest.TestCase):
    def test_decision_and_recovery_states_expose_only_valid_actions(self):
        waiting = project_action_lifecycle(
            {
                "run_id": "run-1",
                "status": "WAITING_FOR_DECISION",
                "decision_evidence": {
                    "decision_id": "decision-1",
                    "allowed_actions": ["approve", "reject", "unknown"],
                },
            }
        )
        self.assertEqual(waiting["schema_version"], ACTION_LIFECYCLE_SCHEMA_VERSION)
        self.assertEqual(waiting["state"], "awaiting_confirmation")
        self.assertEqual(waiting["allowed_actions"], ["approve", "reject"])

        recoverable = project_action_lifecycle(
            {
                "run_id": "run-2",
                "status": "FAILED",
                "failure": {"category": "provider", "retryable": True},
                "retry_count": 1,
            }
        )
        self.assertEqual(recoverable["state"], "recoverable")
        self.assertEqual(
            recoverable["allowed_actions"], ["retry", "recover", "cancel"]
        )
        self.assertEqual(recoverable["attempt"], 2)

    def test_unknown_status_is_not_silent_success(self):
        lifecycle = project_action_lifecycle({"run_id": "run-3"})
        self.assertEqual(lifecycle["state"], "failed")
        self.assertEqual(lifecycle["reason_code"], "run_status_unknown")
        self.assertEqual(lifecycle["allowed_actions"], [])

    def test_result_and_async_projection_share_lifecycle_shape(self):
        payload = {
            "run_id": "run-4",
            "status": "NEEDS_CLARIFICATION",
            "clarification": {"schema_version": "spatial-agent.clarification.v1"},
            "plan": {"output": {"type": "generic_result"}},
            "steps": [],
        }
        result = build_result_contract(payload)
        self.assertEqual(result["lifecycle"]["state"], "clarification_required")

        async_evidence = build_async_result_evidence(
            result, status="NEEDS_CLARIFICATION"
        )
        restored = normalize_async_result_evidence(
            async_evidence, status="NEEDS_CLARIFICATION"
        )
        self.assertEqual(
            restored["lifecycle"]["state"], result["lifecycle"]["state"]
        )
        self.assertEqual(
            restored["lifecycle"]["schema_version"],
            ACTION_LIFECYCLE_SCHEMA_VERSION,
        )

    def test_contract_harness_compares_lifecycle_but_ignores_subject_identity(self):
        payload = {
            "run_id": "run-5",
            "status": "COMPLETED",
            "answer": "完成",
            "plan": {"output": {"type": "generic_result"}},
            "steps": [],
        }
        envelope = build_result_contract(payload)
        first = {**payload, "result": envelope}
        second = {
            **payload,
            "run_id": "run-different",
            "lifecycle": dict(envelope["lifecycle"]),
            "result": dict(envelope),
        }
        self.assertEqual(compare_results([first, second]), [])

        changed_result = dict(envelope)
        changed_result["lifecycle"] = {**envelope["lifecycle"], "state": "failed"}
        changed = {**second, "result": changed_result}
        self.assertTrue(compare_results([first, changed]))


if __name__ == "__main__":
    unittest.main()
