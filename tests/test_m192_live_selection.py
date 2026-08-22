"""Explicit live-model baseline for selection -> facts -> execution.

This test is skipped by default and must never enter the offline CI gate.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.domain_contract import DOMAIN_DISCOVERY_SCHEMA_VERSION
from agent.service import AgentService
from domains.text.domain import TextDomainPack


class FactsRequiredLiveTextDomainPack(TextDomainPack):
    def discover(self, request, request_facts):
        del request, request_facts
        return {
            "schema_version": DOMAIN_DISCOVERY_SCHEMA_VERSION,
            "domain_id": self.domain_id,
            "available": True,
            "selected_capability_id": "text_summary",
            "candidate_ids": ["text_summary"],
            "candidate_count": 1,
        }

    def select_workflow(self, discovery, request_facts, *, workflow=None):
        del discovery, request_facts, workflow
        return {
            "source": "domain_discovery",
            "selected_by": "domain",
            "state": "clarification",
            "selected_capability_id": "text_summary",
            "candidate_ids": ["text_summary"],
            "candidate_count": 1,
            "missing_fields": [{"id": "source", "label": "输入来源", "kind": "fact"}],
        }


@unittest.skipUnless(
    os.environ.get("SPATIAL_AGENT_LIVE_OPENAI") == "1",
    "set SPATIAL_AGENT_LIVE_OPENAI=1 to run the live selection baseline",
)
class M192LiveSelectionTests(unittest.TestCase):
    def test_live_model_selection_to_facts_to_run(self):
        with tempfile.TemporaryDirectory(prefix="m192-live-selection-") as directory:
            root = Path(directory)
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=ArtifactStore(root / "artifacts"),
                domain_pack=FactsRequiredLiveTextDomainPack(),
            )
            try:
                pending = service.run(
                    "请处理这段内容",
                    session_id="m192-live-selection",
                    planner="openai",
                    backend="memory",
                )
                self.assertEqual(pending["status"], "NEEDS_CLARIFICATION")
                completed = service.apply_run_interaction(
                    pending["run_id"],
                    "provide_facts",
                    {
                        "capability_id": "text_summary",
                        "facts": {"source": "这是需要摘要的文本内容"},
                        "require_confirmation": False,
                        "planner": "openai",
                        "backend": "memory",
                    },
                    planner="openai",
                    backend="memory",
                )
            finally:
                service.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["result"]["type"], "text_summary_result")
        self.assertEqual(
            completed["result"]["planning"]["workflow_selection"][
                "selected_capability_id"
            ],
            "text_summary",
        )
        self.assertEqual(
            completed["result"]["model_evidence"]["execution_mode"],
            "live_model",
        )
        self.assertTrue(
            completed["action_receipt"]["transition_identity"]["available"]
        )


if __name__ == "__main__":
    unittest.main()
