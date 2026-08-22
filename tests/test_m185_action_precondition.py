import unittest

from agent.action_precondition import (
    ACTION_PRECONDITION_SCHEMA_VERSION,
    normalize_action_preconditions,
    project_action_preconditions,
)
from agent.execution_timeline import normalize_execution_timeline
from agent.recovery_action import normalize_action_receipt, project_action_receipt
from agent.service_async import build_async_result_evidence, normalize_async_result_evidence
from result_contract import build_result_contract


class M185ActionPreconditionTests(unittest.TestCase):
    def test_receipt_preconditions_are_canonical_over_stale_transport_projection(self):
        canonical = project_action_preconditions(
            {
                "action_receipt": {"action_id": "approve"},
                "action_preconditions": {
                    "conditions": [{"id": "alignment", "status": "ready"}]
                },
            }
        )
        receipt = project_action_receipt(
            {"action_id": "approve", "status": "COMPLETED", "preconditions": canonical}
        )
        result = project_action_preconditions(
            {
                "action_receipt": receipt,
                "action_preconditions": {
                    "conditions": [{"id": "alignment", "status": "unavailable"}]
                },
            }
        )
        self.assertEqual(result, canonical)
        self.assertEqual(
            normalize_action_receipt(receipt)["preconditions"], canonical
        )

    def test_explicit_conditions_are_bounded_and_can_block_a_gated_action(self):
        projection = project_action_preconditions(
            {
                "action_receipt": {"action_id": "approve"},
                "action_preconditions": {
                    "enforce": True,
                    "conditions": [
                        {
                            "id": "alignment",
                            "status": "aligned",
                            "source": "domain.alignment",
                        },
                        {
                            "id": "provenance",
                            "status": "blocked",
                            "reason_code": "source_changed",
                            "private": "must not cross boundary",
                        },
                    ],
                },
            }
        )
        self.assertEqual(
            projection["schema_version"], ACTION_PRECONDITION_SCHEMA_VERSION
        )
        self.assertEqual(projection["state"], "blocked")
        self.assertFalse(projection["action_allowed"])
        self.assertNotIn("private", str(projection))
        self.assertEqual(
            normalize_action_preconditions(projection), projection
        )

    def test_existing_deployment_recovery_and_degradation_states_are_inferred(self):
        projection = project_action_preconditions(
            {
                "result": {
                    "deployment_evidence": {
                        "data": {"runtime_readiness": "degraded"}
                    },
                    "degradation": {"status": "warning"},
                    "evidence_recovery": {
                        "migration": {"state": "legacy_incomplete"}
                    },
                },
                "action_receipt": {"action_id": "retry"},
            }
        )
        self.assertTrue(projection["available"])
        self.assertEqual(projection["state"], "degraded")
        self.assertTrue(projection["action_allowed"])
        self.assertEqual(projection["condition_count"], 3)

    def test_unknown_precondition_schema_degrades_without_interpreting_fields(self):
        projection = normalize_action_preconditions(
            {
                "schema_version": "spatial-agent.action-precondition.v99",
                "state": "ready",
                "conditions": [{"id": "private", "status": "ready"}],
            }
        )
        self.assertFalse(projection["available"])
        self.assertEqual(projection["reason_code"], "action_preconditions_unknown_schema")
        self.assertEqual(projection["conditions"], [])

    def test_text_gis_result_timeline_and_async_keep_preconditions_shape(self):
        for result_type in ("text_summary_result", "spatial_overview_result"):
            payload = {
                "run_id": "m185-" + result_type,
                "request": "开放式请求",
                "result_type": result_type,
                "plan": {"output": {"type": result_type}},
                "status": "COMPLETED",
                "answer": "已完成",
                "steps": [],
                "action_preconditions": {
                    "conditions": [
                        {"id": "data_readiness", "status": "ready"}
                    ]
                },
                "action_receipt": {"action_id": "approve", "status": "COMPLETED"},
            }
            contract = build_result_contract(payload)
            self.assertEqual(
                contract["action_preconditions"]["state"], "ready"
            )
            timeline = normalize_execution_timeline(
                contract["execution_timeline"]
            )
            action = next(
                item for item in timeline["events"] if item["kind"] == "action"
            )
            self.assertEqual(
                action["action_linkage"]["preconditions"]["state"], "ready"
            )
            evidence = normalize_async_result_evidence(
                build_async_result_evidence(contract, status="COMPLETED"),
                status="COMPLETED",
            )
            self.assertEqual(
                evidence["action_preconditions"],
                contract["action_preconditions"],
            )


if __name__ == "__main__":
    unittest.main()
