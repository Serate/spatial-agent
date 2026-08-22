"""M193: transition evidence produces one reusable revalidation status."""

from __future__ import annotations

import unittest

from agent.evidence_revalidation import (
    EVIDENCE_REVALIDATION_SCHEMA_VERSION,
    build_evidence_revalidation,
    normalize_evidence_revalidation,
)
from agent.action_precondition import project_action_preconditions
from agent.execution_timeline import attach_action_receipt_timeline
from agent.recovery_action import project_action_receipt
from agent.transition_evidence import build_transition_evidence
from evaluation.contract_harness import compare_evidence_revalidations


def _transition(result_status: str) -> dict:
    return build_transition_evidence(
        {"data_readiness": "not_ready"},
        {
            "data_readiness": result_status,
            "grid_alignment": {"status": result_status},
        },
    )


class M193EvidenceRevalidationTests(unittest.TestCase):
    def test_changed_evidence_requests_a_new_preview(self):
        projection = build_evidence_revalidation(_transition("ready"))

        self.assertEqual(projection["schema_version"], EVIDENCE_REVALIDATION_SCHEMA_VERSION)
        self.assertEqual(projection["state"], "changed")
        self.assertEqual(projection["next_actions"], ["preview"])

    def test_blocked_evidence_requests_repair_and_keeps_cancel(self):
        projection = build_evidence_revalidation(_transition("not_ready"))

        self.assertEqual(projection["state"], "blocked")
        self.assertEqual(projection["next_actions"], ["repair", "preview", "cancel"])

    def test_receipt_and_timeline_revalidation_are_equal(self):
        receipt = project_action_receipt(
            {
                "action": "provide_facts",
                "status": "COMPLETED",
                "transition_evidence": _transition("ready"),
            }
        )
        payload = attach_action_receipt_timeline({"action_receipt": receipt}, receipt)

        self.assertEqual(
            compare_evidence_revalidations(
                [
                    {"action_receipt": receipt},
                    {"action_receipt": payload["action_receipt"]},
                    {"execution_timeline": payload["execution_timeline"]},
                ]
            ),
            [],
        )
        self.assertEqual(
            normalize_evidence_revalidation(
                receipt["evidence_revalidation"]
            )["state"],
            "changed",
        )

    def test_blocked_revalidation_is_available_to_precondition_projection(self):
        receipt = project_action_receipt(
            {
                "action": "approve",
                "status": "COMPLETED",
                "transition_evidence": _transition("not_ready"),
            }
        )
        preconditions = project_action_preconditions(
            {"action_receipt": receipt},
            action="approve",
        )

        condition = next(
            item
            for item in preconditions["conditions"]
            if item["id"] == "evidence_revalidation"
        )
        self.assertEqual(condition["state"], "blocked")
        self.assertFalse(preconditions["action_allowed"])


if __name__ == "__main__":
    unittest.main()
