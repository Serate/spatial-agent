import unittest

from agent.action_precondition import project_action_preconditions
from agent.action_lifecycle import project_action_lifecycle
from agent.recovery_action import project_action_receipt
from agent.service_async import build_async_result_evidence, normalize_async_result_evidence
from agent.selection_interaction import build_selection_interaction
from evaluation.contract_harness import (
    compare_action_preconditions,
    normalize_action_precondition_contract,
)
from result_contract import build_result_contract


class M186ActionPreconditionContractTests(unittest.TestCase):
    def test_receipt_result_async_and_transport_projections_compare_equally(self):
        canonical = project_action_preconditions({
            "action_receipt": {"action_id": "approve"},
            "action_preconditions": {
                "conditions": [{"id": "alignment", "status": "ready"}]
            },
        })
        receipt = project_action_receipt({
            "action_id": "approve",
            "status": "COMPLETED",
            "preconditions": canonical,
        })
        payloads = [
            {
                "action_receipt": receipt,
                "action_preconditions": {
                    "conditions": [{"id": "alignment", "status": "blocked"}]
                },
            },
            {"result": {"action_preconditions": canonical}},
            {"action_preconditions": canonical},
        ]
        self.assertEqual(compare_action_preconditions(payloads), [])

    def test_precondition_drift_is_reported_without_comparing_timeline_fields(self):
        ready = {"action_preconditions": {
            "conditions": [{"id": "provenance", "status": "ready"}]
        }}
        blocked = {"action_preconditions": {
            "conditions": [{"id": "provenance", "status": "blocked"}]
        }}
        differences = compare_action_preconditions([ready, blocked])
        self.assertTrue(any("state" in item for item in differences))
        self.assertTrue(any("conditions" in item for item in differences))

    def test_unknown_schema_is_safe_and_is_not_treated_as_ready(self):
        contract = normalize_action_precondition_contract({
            "action_preconditions": {
                "schema_version": "spatial-agent.action-precondition.v99",
                "state": "ready",
                "conditions": [{"id": "private", "status": "ready"}],
            }
        })
        self.assertFalse(contract.values["available"])
        self.assertEqual(contract.values["state"], "unknown")
        self.assertEqual(contract.values["conditions"], [])

    def test_enforced_block_removes_execution_actions_and_keeps_safe_exits(self):
        lifecycle = project_action_lifecycle({
            "status": "WAITING_FOR_DECISION",
            "decision_evidence": {
                "status": "PENDING",
                "allowed_actions": ["approve", "reject", "cancel"],
            },
            "action_preconditions": {
                "enforce": True,
                "conditions": [{"id": "alignment", "status": "blocked"}],
            },
        })
        self.assertEqual(lifecycle["allowed_actions"], ["reject", "cancel"])
        self.assertEqual(lifecycle["blocked_actions"], ["approve"])
        self.assertEqual(lifecycle["reason_code"], "action_preconditions_blocked")

    def test_selection_interaction_uses_the_same_enforced_gate(self):
        interaction = build_selection_interaction(
            status="WAITING_FOR_DECISION",
            decision={
                "status": "PENDING",
                "allowed_actions": ["approve", "reject", "cancel"],
            },
            action_preconditions={
                "enforce": True,
                "conditions": [{"id": "alignment", "status": "blocked"}],
            },
        )
        self.assertEqual(interaction["allowed_actions"], ["reject", "cancel"])
        self.assertEqual(interaction["blocked_actions"], ["confirm"])
        self.assertEqual(
            interaction["action_preconditions"]["reason_code"],
            "action_preconditions_blocked",
        )

    def test_result_and_async_recovery_keep_the_same_blocked_interaction(self):
        contract = build_result_contract({
            "status": "WAITING_FOR_DECISION",
            "result_type": "generic_result",
            "decision_evidence": {
                "status": "PENDING",
                "allowed_actions": ["approve", "reject", "cancel"],
            },
            "action_preconditions": {
                "enforce": True,
                "conditions": [{"id": "alignment", "status": "blocked"}],
            },
        })
        async_value = build_async_result_evidence(
            contract, status="WAITING_FOR_DECISION"
        )
        recovered = normalize_async_result_evidence(
            async_value, status="WAITING_FOR_DECISION"
        )
        projections = [
            contract["selection_interaction"],
            async_value["selection_interaction"],
            recovered["selection_interaction"],
        ]
        self.assertEqual({tuple(item["allowed_actions"]) for item in projections}, {
            ("reject", "cancel")
        })
        self.assertEqual({tuple(item["blocked_actions"]) for item in projections}, {
            ("confirm",)
        })


if __name__ == "__main__":
    unittest.main()
