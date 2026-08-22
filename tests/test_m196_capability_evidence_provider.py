"""M196-A: capability evidence is projected behind the provider seam."""

import unittest

from agent.capability_catalog import capability_context_summary
from agent.evidence_contract import (
    CAPABILITY_CATALOG_EVIDENCE_SCHEMA_VERSION,
    CAPABILITY_EVIDENCE_SCHEMA_VERSION,
    normalize_capability_evidence,
    project_capability_catalog_evidence,
)
from agent.runtime_factory import build_runtime
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.text.domain import TEXT_DOMAIN_PACK


class M196CapabilityEvidenceProviderTests(unittest.TestCase):
    def test_provider_observation_is_joined_without_raw_payload(self):
        catalog = {
            "domain_id": "custom",
            "capabilities": [
                {
                    "id": "custom_analysis",
                    "available": True,
                    "dataset_gate": "ready",
                    "datasets": ["records"],
                }
            ],
        }
        projected = project_capability_catalog_evidence(
            catalog,
            runtime_evidence={
                "capabilities_runtime": [
                    {
                        "id": "custom_analysis",
                        "runtime_evidence": {
                            "health_status": "ready",
                            "data_readiness": "ready",
                            "datasets": {
                                "records": {
                                    "status": "ready",
                                    "coverage": {"feature_count": 3},
                                }
                            },
                            "provenance": {"status": "ready", "source": "fixture"},
                        },
                    }
                ]
            },
        )

        self.assertEqual(
            projected["capability_evidence"]["schema_version"],
            CAPABILITY_CATALOG_EVIDENCE_SCHEMA_VERSION,
        )
        evidence = projected["capabilities"][0]["evidence"]
        self.assertEqual(evidence["schema_version"], CAPABILITY_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(evidence["status"], "ready")
        self.assertEqual(evidence["coverage"]["covered_dataset_count"], 1)
        self.assertNotIn("fixture", str(evidence))

    def test_expired_and_conflicting_sources_degrade_boundedly(self):
        catalog = {
            "capabilities": [
                {
                    "id": "custom_analysis",
                    "available": True,
                    "dataset_gate": "ready",
                    "datasets": ["expired", "conflicting"],
                }
            ]
        }
        projected = project_capability_catalog_evidence(
            catalog,
            runtime_evidence={
                "capabilities_runtime": [
                    {
                        "id": "custom_analysis",
                        "runtime_evidence": {
                            "datasets": {
                                "expired": {"status": "expired"},
                                "conflicting": {"status": "conflict"},
                            },
                            "grid_alignment": {"status": "mismatch"},
                        },
                    }
                ]
            },
        )

        evidence = projected["capabilities"][0]["evidence"]
        self.assertEqual(evidence["status"], "unavailable")
        self.assertEqual(evidence["alignment"]["status"], "degraded")
        self.assertLessEqual(len(evidence["missing_reasons"]), 8)

    def test_text_runtime_exposes_the_same_projection_to_context(self):
        runtime = build_runtime("rule", "memory", domain_pack=TEXT_DOMAIN_PACK)
        snapshot = runtime.runtime_capabilities(max_files=1)

        self.assertEqual(
            snapshot["capability_evidence"]["schema_version"],
            CAPABILITY_CATALOG_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(snapshot["capabilities"][0]["evidence"]["status"], "ready")
        context = capability_context_summary(
            catalog=snapshot,
            selected_capability_ids=["text_summary"],
        )
        self.assertEqual(
            context["capabilities"][0]["evidence"],
            snapshot["capabilities"][0]["evidence"],
        )

    def test_gis_runtime_uses_the_same_bounded_projection(self):
        runtime = build_runtime("rule", "memory", domain_pack=GIS_DOMAIN_PACK)
        snapshot = runtime.runtime_capabilities(max_files=1)

        self.assertEqual(
            snapshot["capability_evidence"]["schema_version"],
            CAPABILITY_CATALOG_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertTrue(snapshot["capabilities"])
        for capability in snapshot["capabilities"][:4]:
            self.assertEqual(
                capability["evidence"]["schema_version"],
                CAPABILITY_EVIDENCE_SCHEMA_VERSION,
            )
            self.assertNotIn("runtime_evidence", capability["evidence"])

    def test_unknown_capability_schema_is_safe(self):
        value = normalize_capability_evidence(
            {"schema_version": "future.v9", "status": "ready"}
        )
        self.assertEqual(value["schema_version"], CAPABILITY_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(value["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
