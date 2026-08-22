"""M196-A: capability evidence is projected behind the provider seam."""

import json
import tempfile
import time
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.capability_catalog import capability_context_summary
from agent.evidence_contract import (
    CAPABILITY_CATALOG_EVIDENCE_SCHEMA_VERSION,
    CAPABILITY_EVIDENCE_SCHEMA_VERSION,
    normalize_capability_evidence,
    project_capability_catalog_evidence,
)
from agent.runtime_factory import build_runtime
from agent.service import AgentService
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.text.domain import TEXT_DOMAIN_PACK


class M196CapabilityEvidenceProviderTests(unittest.TestCase):
    @staticmethod
    def _wait_for_terminal(service, run_id):
        for _ in range(300):
            value = service.get_run(run_id)
            if value.get("status") not in {"QUEUED", "PLANNING", "EXECUTING"}:
                return value
            time.sleep(0.01)
        raise AssertionError("async run did not reach a terminal state")

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

    def test_text_run_selection_reuses_provider_evidence(self):
        runtime = build_runtime("rule", "memory", domain_pack=TEXT_DOMAIN_PACK)
        result = runtime.run("概括这段文本")
        candidate = result.plan_evidence["workflow_selection"]["candidate_details"][0]

        self.assertEqual(candidate["id"], "text_summary")
        self.assertEqual(candidate["evidence"]["status"], "ready")
        self.assertEqual(
            candidate["evidence"]["schema_version"],
            CAPABILITY_EVIDENCE_SCHEMA_VERSION,
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

    def test_service_async_and_artifact_preserve_selection_evidence(self):
        with tempfile.TemporaryDirectory(prefix="m196-selection-") as directory:
            root = Path(directory)
            service = AgentService(
                domain_pack=TEXT_DOMAIN_PACK,
                state_db_path=str(root / "state.db"),
                artifact_store=ArtifactStore(root / "artifacts"),
            )
            try:
                direct = service.run(
                    "概括这段文本",
                    session_id="m196-direct",
                    export_artifact=True,
                )
                submitted = service.run_async(
                    request="概括这段文本",
                    session_id="m196-async",
                    export_artifact=True,
                    idempotency_key="m196-selection",
                )
                asynchronous = self._wait_for_terminal(service, submitted["run_id"])
            finally:
                service.close()

            artifact = json.loads(
                Path(direct["artifact_ref"]).read_text(encoding="utf-8")
            )

        def selection(payload):
            return payload["result"]["planning"]["workflow_selection"]

        direct_evidence = selection(direct)["candidate_details"][0]["evidence"]
        async_evidence = selection(asynchronous)["candidate_details"][0]["evidence"]
        artifact_evidence = selection(artifact)["candidate_details"][0]["evidence"]
        self.assertEqual(direct_evidence, async_evidence)
        self.assertEqual(direct_evidence, artifact_evidence)
        self.assertEqual(direct_evidence["status"], "ready")

    def test_unknown_capability_schema_is_safe(self):
        value = normalize_capability_evidence(
            {"schema_version": "future.v9", "status": "ready"}
        )
        self.assertEqual(value["schema_version"], CAPABILITY_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(value["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
