"""M156: execution timeline is a bounded, cross-entry evidence projection."""

import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.execution_timeline import (
    EXECUTION_TIMELINE_SCHEMA_VERSION,
    normalize_execution_timeline,
)
from agent.service_async import build_async_result_evidence, normalize_async_result_evidence
from evaluation.contract_harness import normalize_result
from result_contract import build_result_contract


def _payload():
    return {
        "run_id": "m156-run",
        "status": "COMPLETED",
        "answer": "已完成分析。",
        "result_type": "generic_result",
        "plan": {
            "output": {"type": "generic_result"},
            "steps": [{"id": "answer", "tool": "summarize_text", "args": {}}],
        },
        "plan_evidence": {
            "available": True,
            "plan_quality": {
                "schema_version": "spatial-agent.plan-quality-evidence.v1",
                "available": False,
                "state": "unavailable",
                "passed": True,
                "reason_code": "workflow_blueprint_unavailable",
            },
        },
        "steps": [{
            "id": "answer",
            "tool": "summarize_text",
            "status": "COMPLETED",
            "attempts": 1,
        }],
    }


class M156ExecutionTimelineTests(unittest.TestCase):
    def test_result_timeline_contains_plan_step_and_lifecycle_without_private_text(self):
        payload = _payload()
        payload["error"] = "provider secret must not enter timeline"
        contract = build_result_contract(payload)
        timeline = contract["execution_timeline"]
        self.assertEqual(timeline["schema_version"], EXECUTION_TIMELINE_SCHEMA_VERSION)
        self.assertEqual(
            [item["kind"] for item in timeline["events"]],
            ["planning", "step", "lifecycle"],
        )
        self.assertNotIn("secret", str(timeline).lower())

    def test_async_and_harness_keep_the_same_timeline_projection(self):
        payload = _payload()
        contract = build_result_contract(payload)
        async_evidence = normalize_async_result_evidence(
            build_async_result_evidence(contract, status="COMPLETED"),
            status="COMPLETED",
        )
        self.assertEqual(
            async_evidence["execution_timeline"],
            contract["execution_timeline"],
        )
        normalized = normalize_result({**payload, "result": contract})
        self.assertEqual(
            normalized.as_dict()["execution_timeline"],
            contract["execution_timeline"],
        )

    def test_artifact_persists_timeline_and_unknown_version_degrades(self):
        payload = _payload()
        contract = build_result_contract(payload)
        with tempfile.TemporaryDirectory() as directory:
            artifact = ArtifactStore(directory)
            path = artifact.write_run({**payload, "result": contract})
            stored = artifact.read_run(Path(path).stem)
            self.assertEqual(stored["execution_timeline"], contract["execution_timeline"])
        unknown = normalize_execution_timeline({
            "schema_version": "spatial-agent.execution-timeline.v99",
            "events": [],
        })
        self.assertFalse(unknown["available"])
        self.assertEqual(unknown["reason_code"], "execution_timeline_unknown_schema")


if __name__ == "__main__":
    unittest.main()
