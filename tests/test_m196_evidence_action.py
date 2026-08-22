"""M196-C: Domain evidence advice stays separate from Runtime action gates."""

from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent.artifact_store import ArtifactStore
from agent.models import AgentRunResult, RunStatus, TaskPlan
from agent.selection_interaction import build_selection_interaction
from agent.domain_contract import evidence_action_guidance
from agent.runtime_factory import build_runtime
from agent.service_async import (
    build_async_result_evidence,
    normalize_async_result_evidence,
)
from agent.sqlite_store import SQLiteStateStore
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.text.domain import TEXT_DOMAIN_PACK
from result_contract import build_result_contract
from agent.workflow_selection import (
    EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION,
    build_workflow_selection_evidence,
    normalize_evidence_action_guidance,
)


class M196EvidenceActionTests(unittest.TestCase):
    @staticmethod
    def _guidance_selection():
        return build_workflow_selection_evidence(
            domain_id="example",
            discovery={"candidate_ids": ["capability_a"]},
            evidence_action_guidance={
                "schema_version": EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION,
                "state": "degraded",
                "reason_code": "needs_review",
                "recommended_actions": ["preview", "repair"],
                "source": "domain",
            },
        )

    @classmethod
    def _guidance_contract(cls, run_id):
        selection = cls._guidance_selection()
        return selection, build_result_contract(
            {
                "run_id": run_id,
                "status": "NEEDS_CLARIFICATION",
                "result_type": "text_summary_result",
                "answer": "等待选择",
                "plan": {"output": {"type": "text_summary_result"}},
                "plan_evidence": {"workflow_selection": selection},
                "steps": [],
            }
        )

    def test_guidance_is_bounded_and_keeps_only_action_ids(self):
        selection = build_workflow_selection_evidence(
            domain_id="example",
            discovery={"candidate_ids": ["capability_a"]},
            domain_selection={
                "evidence_action_guidance": {
                    "schema_version": EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION,
                    "state": "degraded",
                    "reason_code": "required_data_missing",
                    "recommended_actions": [
                        "provide_facts",
                        "repair",
                        "not_a_runtime_action",
                    ],
                    "source": "domain",
                }
            },
        )

        guidance = selection["evidence_action_guidance"]
        self.assertEqual(guidance["state"], "degraded")
        self.assertEqual(guidance["recommended_actions"], ["provide_facts", "repair"])
        self.assertEqual(guidance["source"], "domain")

    def test_recommendation_cannot_bypass_selection_lifecycle_gate(self):
        selection = build_workflow_selection_evidence(
            domain_id="example",
            discovery={"candidate_ids": ["capability_a", "capability_b"]},
            evidence_action_guidance={
                "schema_version": EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION,
                "state": "degraded",
                "recommended_actions": ["select_capability", "repair"],
            },
        )
        interaction = build_selection_interaction(
            selection=selection,
            status="NEEDS_CLARIFICATION",
            subject_id="run-1",
        )

        self.assertIn("select_capability", interaction["allowed_actions"])
        recommendations = {
            item["id"]: item for item in interaction["recommended_actions"]
        }
        self.assertEqual(recommendations["select_capability"]["state"], "available")
        self.assertEqual(recommendations["repair"]["state"], "blocked_by_lifecycle")
        self.assertNotIn("repair", interaction["allowed_actions"])

    def test_unknown_guidance_schema_is_safe(self):
        guidance = normalize_evidence_action_guidance(
            {"schema_version": "future.v9", "recommended_actions": ["repair"]}
        )
        self.assertFalse(guidance["available"])
        self.assertEqual(guidance["recommended_actions"], [])
        self.assertEqual(
            guidance["reason_code"], "evidence_action_guidance_unknown_schema"
        )

    def test_domain_adapter_is_advisory_and_hides_provider_failure(self):
        class Domain:
            domain_id = "example"

            def evidence_action_guidance(self, selection, *, request_facts=None):
                del selection, request_facts
                return {
                    "schema_version": EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION,
                    "state": "degraded",
                    "recommended_actions": ["repair"],
                    "source": "domain",
                }

        guidance = evidence_action_guidance(Domain(), {"state": "selected"})
        self.assertEqual(guidance["recommended_actions"], ["repair"])
        self.assertEqual(guidance["source"], "domain")

        class BrokenDomain:
            domain_id = "broken"

            def evidence_action_guidance(self, selection, *, request_facts=None):
                raise RuntimeError("private provider detail")

        failed = evidence_action_guidance(BrokenDomain(), {})
        self.assertEqual(failed["state"], "unavailable")
        self.assertEqual(failed["reason_code"], "domain_evidence_action_guidance_failed")
        self.assertNotIn("private provider detail", str(failed))

    def test_runtime_injects_domain_guidance_into_selection_evidence(self):
        guidance = {
            "schema_version": EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION,
            "state": "degraded",
            "reason_code": "data_needs_review",
            "recommended_actions": ["preview", "repair"],
            "source": "domain",
        }
        with patch.object(
            TEXT_DOMAIN_PACK,
            "evidence_action_guidance",
            return_value=guidance,
            create=True,
        ):
            runtime = build_runtime("rule", "memory", domain_pack=TEXT_DOMAIN_PACK)
            result = runtime.run("概括这段文本")

        projected = result.plan_evidence["workflow_selection"][
            "evidence_action_guidance"
        ]
        self.assertEqual(projected["reason_code"], "data_needs_review")
        self.assertEqual(projected["recommended_actions"], ["preview", "repair"])

    def test_builtin_text_and_gis_domains_supply_the_same_guidance_contract(self):
        for domain in (TEXT_DOMAIN_PACK, GIS_DOMAIN_PACK):
            guidance = evidence_action_guidance(
                domain,
                {
                    "state": "selected",
                    "selected_capability_id": "capability_a",
                    "candidate_details": [],
                },
            )
            self.assertEqual(
                guidance["schema_version"], EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION
            )
            self.assertEqual(guidance["source"], "domain")
            self.assertTrue(guidance["recommended_actions"])

    def test_result_contract_normalizes_guidance_for_planning_and_interaction(self):
        selection = build_workflow_selection_evidence(
            domain_id="example",
            discovery={"candidate_ids": ["capability_a"]},
            evidence_action_guidance={
                "schema_version": EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION,
                "state": "degraded",
                "reason_code": "needs_review",
                "recommended_actions": ["preview", "repair"],
                "source": "domain",
            },
        )
        contract = build_result_contract(
            {
                "status": "NEEDS_CLARIFICATION",
                "result_type": "text_summary_result",
                "answer": "需要进一步选择能力",
                "plan": {"output": {"type": "text_summary_result"}},
                "plan_evidence": {"workflow_selection": selection},
                "steps": [],
            }
        )

        planning_guidance = contract["planning"]["workflow_selection"][
            "evidence_action_guidance"
        ]
        interaction_guidance = contract["selection_interaction"][
            "evidence_action_guidance"
        ]
        self.assertEqual(planning_guidance["reason_code"], "needs_review")
        self.assertEqual(interaction_guidance, planning_guidance)

    def test_async_build_and_recovery_preserve_the_same_guidance_projection(self):
        _, contract = self._guidance_contract("m196-async-guidance")
        async_value = build_async_result_evidence(
            contract, status="NEEDS_CLARIFICATION"
        )
        recovered = normalize_async_result_evidence(
            async_value, status="NEEDS_CLARIFICATION"
        )

        expected = contract["selection_interaction"]
        self.assertEqual(async_value["selection_interaction"], expected)
        self.assertEqual(recovered["selection_interaction"], expected)
        self.assertEqual(
            recovered["planning"]["workflow_selection"][
                "evidence_action_guidance"
            ]["reason_code"],
            "needs_review",
        )

    def test_artifact_round_trip_preserves_guidance_projection(self):
        selection, contract = self._guidance_contract("m196-artifact-guidance")

        with TemporaryDirectory() as root:
            store = ArtifactStore(root)
            store.write_run(
                {
                    "run_id": "m196-artifact-guidance",
                    "domain_id": "example",
                    "status": "NEEDS_CLARIFICATION",
                    "result_type": "text_summary_result",
                    "answer": "等待选择",
                    "plan": {"output": {"type": "text_summary_result"}},
                    "plan_evidence": {"workflow_selection": selection},
                    "result": contract,
                    "steps": [],
                }
            )
            recovered = store.read_run("m196-artifact-guidance", domain_id="example")

        self.assertIsNotNone(recovered)
        self.assertEqual(
            recovered["result"]["selection_interaction"],
            contract["selection_interaction"],
        )
        self.assertEqual(
            recovered["result"]["planning"]["workflow_selection"][
                "evidence_action_guidance"
            ],
            contract["planning"]["workflow_selection"][
                "evidence_action_guidance"
            ],
        )

    def test_sqlite_restart_preserves_guidance_projection(self):
        selection = self._guidance_selection()
        result = AgentRunResult(
            run_id="m196-sqlite-guidance",
            status=RunStatus.NEEDS_CLARIFICATION,
            request="等待选择",
            domain_id="example",
            answer="等待选择",
            plan=TaskPlan(
                goal="等待选择",
                steps=[],
                output={"type": "text_summary_result"},
            ),
            plan_evidence={"workflow_selection": selection},
        )
        expected = build_result_contract(result.to_dict())

        with TemporaryDirectory() as root:
            state_path = f"{root}/state.db"
            SQLiteStateStore(state_path).save(result)
            recovered = SQLiteStateStore(state_path).get(
                result.run_id, domain_id="example"
            )

        self.assertIsNotNone(recovered)
        actual = build_result_contract(recovered.to_dict())
        self.assertEqual(actual["selection_interaction"], expected["selection_interaction"])
        self.assertEqual(actual["planning"], expected["planning"])


if __name__ == "__main__":
    unittest.main()
