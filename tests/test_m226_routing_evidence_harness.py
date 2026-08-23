import copy
import unittest

from agent.contract_versions import DOMAIN_ROUTING_EVIDENCE_SCHEMA_VERSION
from agent.domain_selector import DOMAIN_ROUTING_DECISION_SCHEMA_VERSION
from evaluation.contract_harness import (
    compare_domain_routing_evidence,
    normalize_domain_routing_evidence_contract,
)


def _evidence(*, run_id="run-1", latency=3.25):
    event = {
        "decision_id": "decision-1",
        "parent_decision_id": None,
        "status": "selected",
        "reason_code": "selector_selected",
        "selector_id": "rule.default",
        "candidate_domain_ids": ["gis", "text", "fixture"],
        "selected_domain_id": "gis",
        "selection_source": "automatic",
    }
    return {
        "schema_version": DOMAIN_ROUTING_EVIDENCE_SCHEMA_VERSION,
        "available": True,
        "decision": {
            "schema_version": DOMAIN_ROUTING_DECISION_SCHEMA_VERSION,
            "decision_id": "decision-1",
            "parent_decision_id": None,
            "status": "selected",
            "reason_code": "selector_selected",
            "selector_id": "rule.default",
            "request_fingerprint": "a" * 64,
            "selected_domain_id": "gis",
            "selection_source": "automatic",
        },
        "candidates": [
            {"domain_id": "gis"},
            {"domain_id": "text"},
            {"domain_id": "fixture"},
        ],
        "lineage": {
            "root_decision_id": "decision-1",
            "current_decision_id": "decision-1",
            "event_count": 1,
            "truncated": False,
            "events": [event],
        },
        "binding": {
            "state": "execution_bound",
            "domain_id": "gis",
            "run_id": run_id,
        },
        "observability": {
            "selector_mode": "rule",
            "candidate_count": 3,
            "fallback_reason": None,
            "clarification_required": False,
            "selector_latency_ms": latency,
        },
    }


class M226RoutingEvidenceHarnessTests(unittest.TestCase):
    def test_extracts_result_async_and_artifact_locations(self):
        evidence = _evidence()
        entries = [
            {"domain_routing_evidence": evidence},
            {"result": {"domain_routing_evidence": evidence}},
            {"result_evidence": {"domain_routing_evidence": evidence}},
            {
                "async_observability": {
                    "result_evidence": {"domain_routing_evidence": evidence}
                }
            },
            {"async_result_evidence": {"domain_routing_evidence": evidence}},
            {"artifact": {"domain_routing_evidence": evidence}},
        ]

        self.assertEqual(compare_domain_routing_evidence(entries), [])
        contract = normalize_domain_routing_evidence_contract(entries[0]).as_dict()
        self.assertEqual(contract["identity"]["selected_domain_id"], "gis")
        self.assertEqual(contract["candidates"], ["gis", "text", "fixture"])
        self.assertEqual(contract["lineage"]["current_decision_id"], "decision-1")
        self.assertEqual(contract["binding"]["state"], "execution_bound")

    def test_core_ignores_run_and_latency_but_keeps_routing_semantics(self):
        first = {"domain_routing_evidence": _evidence()}
        second_evidence = _evidence(run_id="run-2", latency=99.0)
        second = {"result": {"domain_routing_evidence": second_evidence}}

        strict_differences = compare_domain_routing_evidence([first, second])
        self.assertIn("entry[1].$.binding.run_id", strict_differences)
        self.assertIn(
            "entry[1].$.observability.selector_latency_ms", strict_differences
        )
        self.assertEqual(compare_domain_routing_evidence([first, second], core=True), [])

        changed = copy.deepcopy(second)
        changed_binding = changed["result"]["domain_routing_evidence"]["binding"]
        changed_binding["state"] = "selected"
        changed_binding["run_id"] = None
        core_differences = compare_domain_routing_evidence([first, changed], core=True)
        self.assertIn("entry[1].$.binding.state", core_differences)

    def test_unknown_schema_is_explicitly_unavailable(self):
        evidence = _evidence()
        evidence["schema_version"] = "spatial-agent.domain-routing-evidence.v999"

        contract = normalize_domain_routing_evidence_contract(
            {"domain_routing_evidence": evidence}
        ).as_dict()

        self.assertFalse(contract["available"])
        self.assertEqual(
            contract["reason_code"], "domain_routing_evidence_unknown_schema"
        )
        self.assertNotIn("identity", contract)


if __name__ == "__main__":
    unittest.main()
