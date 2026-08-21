"""M158: the evidence registry is a shared, versioned reference index."""

import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.evidence_registry import (
    EVIDENCE_REGISTRY_SCHEMA_VERSION,
    build_evidence_registry,
    normalize_evidence_registry,
)
from agent.service_async import build_async_result_evidence, normalize_async_result_evidence
from evaluation.contract_harness import normalize_result
from result_contract import build_result_contract


def _payload():
    return {
        "run_id": "m158-run",
        "status": "COMPLETED",
        "answer": "已完成。",
        "result_type": "generic_result",
        "plan": {"output": {"type": "generic_result"}, "steps": []},
        "steps": [],
        "plan_evidence": {"available": False},
    }


class M158EvidenceRegistryTests(unittest.TestCase):
    def test_registry_names_versions_and_json_references(self):
        contract = build_result_contract(_payload())
        registry = contract["evidence_registry"]
        self.assertEqual(registry["schema_version"], EVIDENCE_REGISTRY_SCHEMA_VERSION)
        self.assertEqual(registry["entry_count"], 5)
        self.assertEqual(
            {item["id"] for item in registry["entries"]},
            {"result", "plan_quality", "execution_timeline", "action_lifecycle", "replanning"},
        )
        self.assertTrue(all(item["reference"].startswith(("result",)) for item in registry["entries"]))

    def test_result_async_artifact_and_harness_share_registry(self):
        payload = _payload()
        contract = build_result_contract(payload)
        async_evidence = normalize_async_result_evidence(
            build_async_result_evidence(contract, status="COMPLETED"),
            status="COMPLETED",
        )
        self.assertEqual(async_evidence["evidence_registry"], contract["evidence_registry"])
        normalized = normalize_result({**payload, "result": contract})
        self.assertEqual(normalized.as_dict()["evidence_registry"], contract["evidence_registry"])
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(directory)
            path = store.write_run({**payload, "result": contract})
            stored = store.read_run(Path(path).stem)
            self.assertEqual(stored["evidence_registry"], contract["evidence_registry"])

    def test_unknown_registry_version_is_unavailable(self):
        result = normalize_evidence_registry({
            "schema_version": "spatial-agent.evidence-registry.v99",
            "entries": [],
        })
        self.assertFalse(result["available"])
        self.assertEqual(result["reason_code"], "evidence_registry_unknown_schema")

    def test_unknown_entry_schema_or_external_reference_is_unavailable(self):
        base = {
            "schema_version": EVIDENCE_REGISTRY_SCHEMA_VERSION,
            "available": True,
            "entries": [{
                "id": "future",
                "schema_version": "spatial-agent.future.v9",
                "available": True,
                "state": "available",
                "reference": "result.future",
            }],
        }
        unknown_schema = normalize_evidence_registry(base)
        self.assertEqual(unknown_schema["reason_code"], "evidence_registry_unknown_entry_schema")
        base["entries"][0]["schema_version"] = "spatial-agent.result-envelope.v1"
        base["entries"][0]["reference"] = "file:///private"
        invalid_reference = normalize_evidence_registry(base)
        self.assertEqual(invalid_reference["reason_code"], "evidence_registry_reference_invalid")


if __name__ == "__main__":
    unittest.main()
