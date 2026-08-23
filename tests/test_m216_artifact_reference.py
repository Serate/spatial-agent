import unittest

from agent.artifact_reference import (
    ARTIFACT_REFERENCE_SCHEMA_VERSION,
    build_artifact_reference,
    normalize_artifact_reference,
)
from agent.service_async import build_async_result_evidence
from agent.nested_schema import normalize_result_contract
from result_contract import build_result_contract


class M216ArtifactReferenceTests(unittest.TestCase):
    def test_result_contract_exposes_portable_geometry_reference(self):
        contract = build_result_contract(
            {
                "run_id": "m216-reference",
                "status": "COMPLETED",
                "result_type": "admin_area_result",
                "answer": "已生成有界空间摘要。",
                "artifact_ref": r"D:\outputs\runs\m216-reference.json",
                "geojson_ref": r"D:\outputs\geojson\m216-reference.geojson",
                "_geometry_evidence": {
                    "status": "truncated_geometry",
                    "reason": "达到输出预算",
                    "feature_count": 79,
                    "truncated": True,
                    "sources": ["geopackage"],
                },
                "steps": [],
            }
        )

        reference = contract["geometry"]["reference"]
        self.assertEqual(reference["schema_version"], ARTIFACT_REFERENCE_SCHEMA_VERSION)
        self.assertEqual(reference["ref"], "m216-reference.geojson")
        self.assertEqual(reference["status"], "truncated_geometry")
        self.assertTrue(reference["truncated"])
        self.assertEqual(
            reference["access"]["path"],
            "/artifacts/geojson/m216-reference.geojson",
        )
        self.assertNotIn("D:", str(reference))
        self.assertEqual(
            contract["artifacts"]["run"]["ref"], "m216-reference.json"
        )

        restored = normalize_result_contract(contract)
        self.assertEqual(
            restored["geometry"]["reference"], contract["geometry"]["reference"]
        )
        self.assertEqual(
            restored["references"][-1]["artifact_reference"], reference
        )

    def test_async_evidence_keeps_only_safe_artifact_locator(self):
        evidence = build_async_result_evidence(
            {"available": True},
            status="COMPLETED",
            artifact_ref=r"D:\outputs\runs\m216-async.json",
        )
        reference = evidence["artifact"]["reference"]
        self.assertEqual(reference["ref"], "m216-async.json")
        self.assertEqual(
            reference["access"]["path"], "/artifacts/runs/m216-async.json"
        )
        self.assertNotIn("D:", str(evidence))

    def test_normalizer_rejects_host_path_in_persisted_reference(self):
        normalized = normalize_artifact_reference(
            {
                "schema_version": ARTIFACT_REFERENCE_SCHEMA_VERSION,
                "kind": "geojson",
                "ref": "../private.geojson",
            }
        )
        self.assertFalse(normalized["available"])
        self.assertEqual(normalized["reason_code"], "artifact_ref_not_portable")
        self.assertIsNone(normalized.get("access"))

        generated = build_artifact_reference(
            r"D:\outputs\geojson\safe.geojson", kind="geojson"
        )
        self.assertEqual(generated["ref"], "safe.geojson")


if __name__ == "__main__":
    unittest.main()
