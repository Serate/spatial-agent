"""M192-B: data evidence changes remain bounded across a selection transition."""

from __future__ import annotations

import unittest

from agent.execution_timeline import attach_action_receipt_timeline, normalize_execution_timeline
from agent.recovery_action import project_action_receipt
from agent.transition_evidence import (
    TRANSITION_EVIDENCE_SCHEMA_VERSION,
    build_transition_evidence,
    normalize_transition_evidence,
    project_transition_evidence,
)
from evaluation.contract_harness import compare_action_transition_evidence


def _source_payload() -> dict:
    return {
        "result": {
            "data_readiness": "not_ready",
            "provenance": {
                "status": "recorded",
                "fingerprint": "sha256:source-data",
            },
        }
    }


def _result_payload() -> dict:
    return {
        "result": {
            "steps": [
                {
                    "result": {
                        "data_readiness": "ready",
                        "grid_alignment": {
                            "status": "aligned",
                            "metadata_only": True,
                        },
                        "provenance": {
                            "status": "verified",
                            "fingerprint": "sha256:result-data",
                            "datasets": ["dem", "land_use"],
                        },
                    }
                }
            ]
        }
    }


class M192TransitionEvidenceTests(unittest.TestCase):
    def test_projection_is_bounded_and_reports_changed_fields(self):
        transition = build_transition_evidence(
            _source_payload(),
            _result_payload(),
        )

        self.assertEqual(
            transition["schema_version"],
            TRANSITION_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(transition["state"], "changed")
        self.assertEqual(
            {item["field"] for item in transition["changes"]},
            {"readiness", "alignment", "provenance"},
        )
        self.assertIn("sha256:source-data", str(transition))
        self.assertIn("sha256:result-data", str(transition))
        self.assertNotIn("/", str(transition))

    def test_receipt_and_timeline_keep_the_same_transition_evidence(self):
        transition = build_transition_evidence(_source_payload(), _result_payload())
        receipt = project_action_receipt(
            {
                "action": "provide_facts",
                "status": "COMPLETED",
                "run_id": "source-run",
                "result_run_id": "result-run",
                "transition_evidence": transition,
            }
        )
        payload = attach_action_receipt_timeline(
            {"action_receipt": receipt},
            receipt,
        )
        timeline = normalize_execution_timeline(payload["execution_timeline"])
        action = next(item for item in timeline["events"] if item["kind"] == "action")

        self.assertEqual(
            compare_action_transition_evidence(
                [
                    {"action_receipt": receipt},
                    {"action_receipt": payload["action_receipt"]},
                    {"execution_timeline": payload["execution_timeline"]},
                ]
            ),
            [],
        )
        self.assertEqual(
            action["action_linkage"]["transition_evidence"]["state"],
            "changed",
        )

    def test_unknown_schema_is_unavailable_without_copying_fields(self):
        self.assertIsNone(
            normalize_transition_evidence(
                {
                    "schema_version": "spatial-agent.action-transition-evidence.v9",
                    "fields": {"provenance": [{"secret": "must-not-cross"}]},
                }
            )
        )
        projection = project_transition_evidence({"future": {"secret": "ignored"}})
        self.assertFalse(projection["available"])
        self.assertNotIn("must-not-cross", str(projection))


if __name__ == "__main__":
    unittest.main()
