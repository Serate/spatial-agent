"""M196-C: Domain evidence advice stays separate from Runtime action gates."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from agent.selection_interaction import build_selection_interaction
from agent.domain_contract import evidence_action_guidance
from agent.runtime_factory import build_runtime
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.text.domain import TEXT_DOMAIN_PACK
from agent.workflow_selection import (
    EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION,
    build_workflow_selection_evidence,
    normalize_evidence_action_guidance,
)


class M196EvidenceActionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
