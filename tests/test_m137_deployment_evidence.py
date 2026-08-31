"""M137 release/runtime evidence binding checks."""

import json
import unittest

from agent.service import AgentService
from agent.deployment_evidence import build_deployment_evidence
from domains.text.runtime import build_text_runtime
from evaluation.model_evaluation import evaluate_model_fixture_file
from result_contract import build_result_contract


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


class M137DeploymentEvidenceTests(unittest.TestCase):
    def test_text_runtime_and_release_evidence_share_context_identity(self):
        service = AgentService(runtime_factory=_text_runtime_factory, domain_id="text")
        try:
            runtime = service.runtime_capabilities(planner="rule", backend="memory")
            release = service.release_evidence(planner="rule", backend="memory")
        finally:
            service.close()

        self.assertEqual(runtime["domain_id"], "text")
        self.assertEqual(release["domain_id"], "text")
        self.assertEqual(
            runtime["runtime_context_fingerprint"],
            runtime["runtime_context"]["fingerprint"],
        )
        self.assertEqual(
            release["runtime_context_fingerprint"],
            release["runtime_context"]["fingerprint"],
        )
        self.assertEqual(
            runtime["runtime_context_fingerprint"],
            release["runtime_context_fingerprint"],
        )
        self.assertEqual(release["evidence_contract"]["kind"], "release")
        self.assertEqual(release["evidence_contract"]["domain_id"], "text")
        self.assertEqual(
            release["deployment_evidence"]["context_fingerprint"],
            release["runtime_context_fingerprint"],
        )

    def test_gis_release_evidence_keeps_degradation_and_context_separate(self):
        service = AgentService()
        try:
            release = service.release_evidence(planner="rule", backend="memory")
        finally:
            service.close()

        self.assertEqual(release["domain_id"], "gis")
        self.assertEqual(release["evidence_contract"]["kind"], "release")
        self.assertIn(
            release["status"],
            {"ready", "degraded", "unavailable", "not_configured", "unknown"},
        )
        self.assertTrue(release["runtime_context_fingerprint"].startswith("sha256:"))
        self.assertEqual(
            release["runtime_context"]["fingerprint"],
            release["runtime_context_fingerprint"],
        )
        self.assertEqual(
            release["deployment_evidence"]["context_fingerprint"],
            release["runtime_context_fingerprint"],
        )
        encoded = json.dumps(release, ensure_ascii=False)
        self.assertNotIn("api_key", encoded.lower())
        self.assertNotIn("authorization", encoded.lower())

    def test_offline_replay_model_identity_is_bounded_and_versioned(self):
        report = evaluate_model_fixture_file(
            "tests/fixtures/m67_spatial_overview_model.json"
        )

        self.assertTrue(report["passed"])
        evidence = report["model_evidence"]
        self.assertEqual(evidence["execution_mode"], "offline_replay")
        self.assertEqual(evidence["fixture_id"], "m67-spatial-overview-redacted")
        self.assertEqual(evidence["schema_version"], "spatial-agent.model-evidence.v1")
        self.assertNotIn("response", json.dumps(evidence, ensure_ascii=False))

        contract = build_result_contract(
            {
                "result_type": "text_summary_result",
                "planner_metrics": {
                    "execution_mode": "offline_replay",
                    "fixture_id": "fixture-safe",
                    "raw_response": "must not be copied",
                },
            }
        )
        self.assertEqual(contract["model_evidence"]["fixture_id"], "fixture-safe")
        self.assertNotIn("raw_response", json.dumps(contract["model_evidence"]))

    def test_deployment_projection_filters_raw_model_metrics(self):
        evidence = build_deployment_evidence(
            {"runtime_context": {"domain_id": "text", "planner": "rule"}},
            model_evidence={
                "execution_mode": "live_model",
                "provider": "provider-safe",
                "raw_response": "must not be copied",
                "api_key": "sk-never-return-this",
                "private_path": "D:/private/provider.json",
            },
        )

        encoded = json.dumps(evidence, ensure_ascii=False)
        self.assertIn("provider-safe", encoded)
        self.assertNotIn("raw_response", encoded)
        self.assertNotIn("sk-never-return-this", encoded)
        self.assertNotIn("private_path", encoded)


if __name__ == "__main__":
    unittest.main()
