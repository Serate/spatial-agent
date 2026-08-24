"""M168: candidate data evidence and Domain workflow seams are versioned."""

from pathlib import Path
import tempfile
import time
import unittest

from agent.artifact_store import ArtifactStore
from agent.domain_contract import (
    DOMAIN_WORKFLOW_SEAM_SCHEMA_VERSION,
    workflow_seam_summary,
)
from agent.evidence_contract import (
    CAPABILITY_EVIDENCE_SCHEMA_VERSION,
    build_capability_evidence,
    normalize_capability_evidence,
)
from agent.runtime_factory import build_runtime
from agent.service import AgentService
from agent.workflow_selection import normalize_workflow_selection_evidence
from domains.text.domain import TEXT_DOMAIN_PACK
from domains.text.runtime import build_text_runtime
from evaluation.contract_harness import compare_results


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


def _wait_for_terminal(service, run_id):
    for _ in range(200):
        value = service.get_run(run_id)
        if value.get("status") not in {"QUEUED", "PLANNING", "EXECUTING"}:
            return value
        time.sleep(0.01)
    raise AssertionError("async run did not reach a terminal state")


class M168CapabilityEvidenceTests(unittest.TestCase):
    def test_missing_catalog_data_becomes_bounded_unavailable_evidence(self):
        evidence = build_capability_evidence(
            {
                "available": False,
                "dataset_gate": "missing",
                "missing_datasets": ["private-path-is-not-exposed"],
                "datasets": ["records"],
            }
        )
        self.assertEqual(evidence["schema_version"], CAPABILITY_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(evidence["status"], "unavailable")
        self.assertEqual(evidence["readiness"]["status"], "unavailable")
        self.assertIn("缺少数据：private-path-is-not-exposed", evidence["missing_reasons"])
        restored = normalize_capability_evidence(evidence)
        self.assertEqual(restored, evidence)

    def test_text_selection_carries_evidence_and_seam_versions(self):
        runtime = build_runtime("rule", "memory", domain_pack=TEXT_DOMAIN_PACK)
        result = runtime.run("概括这段文本")
        selection = result.plan_evidence["workflow_selection"]
        self.assertEqual(
            selection["domain_seams"]["schema_version"],
            DOMAIN_WORKFLOW_SEAM_SCHEMA_VERSION,
        )
        self.assertTrue(selection["domain_seams"]["capability_resolution"])
        candidate = selection["candidate_details"][0]
        self.assertEqual(
            candidate["evidence"]["schema_version"],
            CAPABILITY_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertNotIn("/", str(candidate["evidence"]))
        self.assertEqual(
            normalize_workflow_selection_evidence(selection), selection
        )

    def test_seam_summary_is_small_and_domain_owned(self):
        summary = workflow_seam_summary(TEXT_DOMAIN_PACK)
        self.assertEqual(summary["schema_version"], DOMAIN_WORKFLOW_SEAM_SCHEMA_VERSION)
        self.assertEqual(
            set(summary) - {"schema_version", "selection", "workflow_normalization", "plan_validation", "capability_resolution"},
            set(),
        )

    def test_console_and_contract_references_are_domain_neutral(self):
        root = Path(__file__).parents[1]
        module = (root / "web" / "src" / "console_interaction.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("spatial-agent.interaction.v1", module)
        self.assertIn("function candidates", module)
        self.assertNotIn("admin_name", module)

    def test_unknown_capability_evidence_schema_degrades_safely(self):
        value = normalize_capability_evidence(
            {"schema_version": "future.v9", "status": "ready"}
        )
        self.assertEqual(value["schema_version"], CAPABILITY_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(value["status"], "unavailable")
        self.assertEqual(value["readiness"]["status"], "unknown")

    def test_candidate_evidence_survives_sync_async_contract(self):
        with tempfile.TemporaryDirectory(prefix="m168-evidence-") as directory:
            root = Path(directory)
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=ArtifactStore(root / "artifacts"),
                runtime_factory=_text_runtime_factory,
            )
            try:
                request = "请概括：证据需要跨入口保持一致。"
                direct = service.run(
                    request=request,
                    session_id="m168-sync",
                    planner="rule",
                    backend="memory",
                    export_artifact=True,
                )
                submitted = service.run_async(
                    request=request,
                    session_id="m168-async",
                    planner="rule",
                    backend="memory",
                    export_artifact=True,
                    idempotency_key="m168-evidence",
                )
                asynchronous = _wait_for_terminal(service, submitted["run_id"])
            finally:
                service.close()
        self.assertEqual(compare_results([direct, asynchronous]), [])
        candidate = direct["result"]["planning"]["workflow_selection"]["candidate_details"][0]
        self.assertEqual(candidate["evidence"]["schema_version"], CAPABILITY_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(
            asynchronous["result"]["planning"]["workflow_selection"]["domain_seams"],
            direct["result"]["planning"]["workflow_selection"]["domain_seams"],
        )


if __name__ == "__main__":
    unittest.main()
