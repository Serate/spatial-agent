"""M181: lifecycle, interaction, and evidence actions share one receipt seam."""

import unittest

from agent.recovery_action import (
    ACTION_RECEIPT_SCHEMA_VERSION,
    RECOVERY_ACTION_SCHEMA_VERSION,
    action_input_fingerprint,
    normalize_action_ids,
    project_action_receipt,
    project_available_actions,
    project_legacy_interaction_receipt,
)
from agent.action_lifecycle import project_action_lifecycle
from agent.decision_lifecycle import build_decision_evidence
from agent.selection_interaction import build_selection_interaction
from result_contract import build_result_contract


class M181RecoveryActionTests(unittest.TestCase):
    def test_action_catalog_is_bounded_and_classifies_shared_lifecycle(self):
        actions = project_available_actions(
            ["retry", "rebuild_from_result", "cancel", "retry", "unknown"],
            subject_id="m181-run",
        )

        self.assertEqual([item["id"] for item in actions], [
            "retry", "rebuild_from_result", "cancel"
        ])
        self.assertEqual(actions[0]["schema_version"], RECOVERY_ACTION_SCHEMA_VERSION)
        self.assertEqual(actions[0]["kind"], "lifecycle")
        self.assertEqual(actions[1]["kind"], "evidence_recovery")
        self.assertTrue(all(item["idempotency_required"] for item in actions))

    def test_selection_projection_exposes_same_action_descriptors(self):
        interaction = build_selection_interaction(
            status="NEEDS_CLARIFICATION", subject_id="m181-run"
        )

        self.assertEqual(
            interaction["allowed_actions"],
            ["select_capability", "select_workflow", "cancel"],
        )
        self.assertEqual(
            [item["id"] for item in interaction["actions"]],
            interaction["allowed_actions"],
        )
        self.assertTrue(all(item["subject_id"] == "m181-run" for item in interaction["actions"]))
        self.assertEqual(interaction["actions"][0]["kind"], "interaction")

    def test_lifecycle_and_decision_use_the_same_action_descriptor(self):
        lifecycle = project_action_lifecycle({
            "run_id": "m181-run",
            "status": "FAILED",
            "failure": {"retryable": True},
        })
        decision = build_decision_evidence(
            "awaiting_confirmation",
            allowed_actions=("approve", "reject"),
            run_id="m181-run",
        )

        self.assertEqual(
            [item["id"] for item in lifecycle["actions"]],
            lifecycle["allowed_actions"],
        )
        self.assertEqual(
            [item["id"] for item in decision["actions"]],
            decision["allowed_actions"],
        )
        self.assertEqual(lifecycle["actions"][0]["kind"], "lifecycle")
        self.assertEqual(decision["actions"][0]["kind"], "decision")

    def test_receipt_projection_and_fingerprint_are_shared_and_safe(self):
        fingerprint_a = action_input_fingerprint(
            "rebuild_from_result", {"run_id": "m181-run", "secret": "hidden"}
        )
        fingerprint_b = action_input_fingerprint(
            "rebuild_from_result", {"secret": "hidden", "run_id": "m181-run"}
        )
        receipt = {
            "domain_id": "text",
            "run_id": "m181-run",
            "action": "rebuild_from_result",
            "idempotency_key": "m181-rebuild-1",
            "input_fingerprint": fingerprint_a,
            "status": "COMPLETED",
            "result_run_id": "m181-run",
        }

        self.assertEqual(fingerprint_a, fingerprint_b)
        projected = project_action_receipt(receipt, reused=True)
        self.assertEqual(projected["schema_version"], ACTION_RECEIPT_SCHEMA_VERSION)
        self.assertEqual(projected["action_id"], "rebuild_from_result")
        self.assertEqual(projected["action_kind"], "evidence_recovery")
        self.assertTrue(projected["reused"])
        self.assertNotIn("secret", str(projected))

        legacy = project_legacy_interaction_receipt(receipt, reused=True)
        self.assertEqual(legacy["schema_version"], "spatial-agent.interaction-receipt.v1")
        self.assertEqual(legacy["action"], projected["action_id"])

    def test_result_contract_keeps_generic_receipt_without_replacing_legacy_fields(self):
        receipt = project_action_receipt({
            "run_id": "m181-result",
            "action": "retry",
            "status": "COMPLETED",
            "idempotency_key": "m181-retry-1",
        })
        contract = build_result_contract({
            "run_id": "m181-result",
            "domain_id": "text",
            "status": "COMPLETED",
            "answer": "已完成。",
            "plan": {"steps": [], "output": {"type": "text_summary_result"}},
            "steps": [],
            "action_receipt": receipt,
        })

        self.assertEqual(contract["action_receipt"], receipt)
        self.assertEqual(normalize_action_ids(["retry", "cancel"], allowed={"retry", "cancel"}), ["retry", "cancel"])


if __name__ == "__main__":
    unittest.main()
