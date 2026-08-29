"""Compact M327-D contract checks for shared result-summary consumption."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.application.service_async import (
    build_async_result_evidence,
    normalize_async_result_evidence,
)
from agent.application.run_recovery import RunRecoveryApplication
from agent.persistence.artifact_store import ArtifactStore
from agent.result_summary import RESULT_SUMMARY_SCHEMA_VERSION
from result_contract import build_result_contract


def _profile(*kinds: str) -> dict[str, object]:
    return {
        "schema_version": "spatial-agent.data-profile.v1",
        "primary": kinds[0],
        "kinds": list(kinds),
    }


def _payload() -> dict[str, object]:
    return {
        "run_id": "m327-cross-entry",
        "domain_id": "gis",
        "status": "COMPLETED",
        "request": "跨入口结果摘要",
        "answer": "各入口都应看到同一份摘要。",
        "plan": {"output": {"type": "summary_result"}, "steps": []},
        "steps": [],
        "typed_sections": [
            {
                "block_id": "metrics",
                "title": "指标结果",
                "data_profile": _profile("metrics"),
                "state": "completed",
                "conclusion": "指标结果已整理。",
                "facts": {"count": 3, "minimum": 1.23456789},
                "evidence": {"available": True, "sources": ["fixture-source"]},
            }
        ],
    }


class M327CrossEntryProjectionTests(unittest.TestCase):
    def test_async_projection_keeps_the_canonical_summary(self):
        contract = build_result_contract(_payload())
        evidence = build_async_result_evidence(contract, status="COMPLETED")
        self.assertEqual(
            evidence["result_summary"], contract["result_summary"]
        )
        restored = normalize_async_result_evidence(evidence, status="COMPLETED")
        self.assertEqual(restored["result_summary"], contract["result_summary"])
        self.assertEqual(
            restored["result_summary"]["schema_version"],
            RESULT_SUMMARY_SCHEMA_VERSION,
        )

    def test_artifact_and_recovery_evidence_expose_the_same_summary(self):
        contract = build_result_contract(_payload())
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(str(Path(directory) / "runs"))
            artifact_ref = store.write_run({**_payload(), "result": contract})
            artifact = store.read_run("m327-cross-entry", domain_id="gis")
            self.assertIsNotNone(artifact)
            self.assertEqual(artifact["result_summary"], contract["result_summary"])
            self.assertEqual(
                artifact["result"]["result_summary"], contract["result_summary"]
            )

            class _State:
                persistent = False

            recovery = RunRecoveryApplication(
                artifact_store=store,
                state=_State(),
                runtime_provider=lambda _planner, _backend: object(),
                domain_id_provider=lambda _planner, _backend: "gis",
                resolved_domain_id=lambda: "gis",
                configured_domain_id=lambda: "gis",
                reserve_action_receipt=lambda **_kwargs: None,
                complete_action_receipt=lambda *_args, **_kwargs: None,
                attach_async_observability=lambda *_args: None,
                mark_memory_cancel_requested=lambda _run_id: None,
            )
            evidence = recovery.get_run_evidence("m327-cross-entry")
            self.assertEqual(evidence["result_summary"], contract["result_summary"])
            self.assertTrue(artifact_ref.endswith("m327-cross-entry.json"))


if __name__ == "__main__":
    unittest.main()
