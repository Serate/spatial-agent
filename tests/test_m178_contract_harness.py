"""M178: Contract Harness consumes the shared evidence projection seam."""

from copy import deepcopy
import unittest

from agent.evidence_projection import project_evidence_projection
from agent.service_async import build_async_result_evidence
from evaluation.contract_harness import compare_results, normalize_result
from result_contract import build_result_contract


def _payload(domain_id="text"):
    return {
        "run_id": f"m178-{domain_id}",
        "domain_id": domain_id,
        "status": "COMPLETED",
        "answer": "已完成。",
        "result_type": "text_summary_result",
        "plan": {
            "goal": "完成结构化任务",
            "steps": [],
            "output": {"type": "text_summary_result"},
        },
        "steps": [],
        "trace_summary": [],
        "plan_evidence": {
            "available": True,
            "workflow_selection": {
                "schema_version": "spatial-agent.workflow-selection.v1",
                "state": "selected",
                "reason_code": "workflow_selected",
                "source": "domain_discovery",
                "selected_capability_id": "text_summary",
                "candidate_ids": ["text_summary"],
            },
            "planner_selection": {
                "schema_version": "spatial-agent.planner-selection.v1",
                "state": "matched",
                "reason_code": "planner_matches_selected_capability",
                "result_type": "text_summary_result",
                "selected_capability_id": "text_summary",
                "planner_capability_id": "text_summary",
                "planner_kind": "RuleBasedPlanner",
                "candidate_ids": ["text_summary"],
            },
        },
    }


def _full_payload(domain_id="text"):
    payload = _payload(domain_id)
    return {**payload, "result": build_result_contract(payload)}


class M178ContractHarnessTests(unittest.TestCase):
    def test_sync_and_async_use_the_same_evidence_projection(self):
        sync = _full_payload()
        async_evidence = build_async_result_evidence(
            sync["result"], status="COMPLETED", artifact_ref="run.json"
        )
        async_payload = {
            **sync,
            "async_observability": {"result_evidence": async_evidence},
        }

        sync_projection = normalize_result(sync).as_dict()["evidence_projection"]
        async_projection = normalize_result(async_payload).as_dict()[
            "async_result_evidence"
        ]["evidence_projection"]

        self.assertEqual(sync_projection, async_projection)
        self.assertEqual(compare_results([sync, async_payload]), [])

        artifact_only = {
            "status": sync["status"],
            "answer": sync["answer"],
            "result": sync["result"],
            "artifact_schema_version": "spatial-agent.run-artifact.v1",
            "artifact_ref": "recovered-run.json",
        }
        self.assertEqual(
            project_evidence_projection(artifact_only), sync_projection
        )

    def test_text_and_gis_have_the_same_projection_shape(self):
        text = normalize_result(_full_payload("text")).as_dict()[
            "evidence_projection"
        ]
        gis = normalize_result(_full_payload("gis")).as_dict()[
            "evidence_projection"
        ]

        self.assertEqual(set(text), set(gis))
        self.assertEqual(set(text["selection"]), set(gis["selection"]))
        self.assertEqual(set(text["migration"]), set(gis["migration"]))
        self.assertEqual(text["schema_version"], gis["schema_version"])

    def test_legacy_and_unknown_registry_states_are_visible_to_harness(self):
        current = _full_payload()
        legacy = deepcopy(current)
        registry = legacy["result"]["evidence_registry"]
        registry["entries"] = [
            item
            for item in registry["entries"]
            if item["id"] not in {"workflow_selection", "planner_selection"}
        ]
        registry["entry_count"] = len(registry["entries"])
        legacy_projection = normalize_result(legacy).as_dict()[
            "evidence_projection"
        ]
        self.assertEqual(
            legacy_projection["migration"]["state"], "legacy_incomplete"
        )
        self.assertTrue(legacy_projection["migration"]["migratable"])

        unknown = deepcopy(current)
        unknown["result"]["evidence_registry"]["schema_version"] = (
            "spatial-agent.evidence-registry.v99"
        )
        unknown_projection = normalize_result(unknown).as_dict()[
            "evidence_projection"
        ]
        self.assertEqual(
            unknown_projection["migration"]["state"], "unknown_schema"
        )
        self.assertFalse(unknown_projection["migration"]["migratable"])

    def test_planner_selection_drift_is_reported_through_projection(self):
        changed = _full_payload()
        changed["result"]["planning"]["planner_selection"]["state"] = "mismatch"
        changed["result"]["planning"]["planner_selection"]["reason_code"] = (
            "planner_result_type_unknown"
        )

        differences = compare_results([_full_payload(), changed])

        self.assertTrue(
            any(
                "$.evidence_projection.selection.planner_selection.state" in item
                for item in differences
            ),
            differences,
        )


if __name__ == "__main__":
    unittest.main()
