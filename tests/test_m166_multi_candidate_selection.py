"""M166: Domain-declared ambiguity must become a resumable Runtime choice."""

from __future__ import annotations

import unittest
import tempfile
import time
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.domain_contract import DOMAIN_DISCOVERY_SCHEMA_VERSION
from agent.service import AgentService
from domains.text.runtime import build_text_runtime
from domains.text.domain import TextDomainPack
from evaluation.contract_harness import compare_results


class AmbiguousTextDomainPack(TextDomainPack):
    """Small domain fixture proving the generic ambiguity seam.

    The fixture intentionally returns two candidates without choosing one.
    It does not add Runtime or transport logic and uses the normal Text
    planner after the caller selects a workflow.
    """

    def discover(self, request, request_facts):
        del request, request_facts
        return {
            "schema_version": DOMAIN_DISCOVERY_SCHEMA_VERSION,
            "domain_id": self.domain_id,
            "available": True,
            "selected_capability_id": None,
            "candidate_ids": ["text_summary", "text_summary_alt"],
            "candidate_count": 2,
        }

    def select_workflow(self, discovery, request_facts, *, workflow=None):
        del discovery, request_facts
        if workflow and workflow.get("template_id"):
            return {
                "source": "explicit_workflow",
                "selected_by": "user",
                "selected_capability_id": "text_summary",
                "candidate_ids": ["text_summary"],
                "candidate_count": 1,
            }
        return {
            "source": "domain_discovery",
            "selected_by": "domain",
            "state": "ambiguous",
            "selected_capability_id": None,
            "candidate_ids": ["text_summary", "text_summary_alt"],
            "candidate_count": 2,
        }


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


def _wait_for_terminal(service, run_id):
    for _ in range(200):
        payload = service.get_run(run_id)
        if payload.get("status") not in {"PLANNING", "EXECUTING"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("async text run did not complete")

class M166MultiCandidateSelectionTests(unittest.TestCase):
    def test_ambiguous_domain_stops_before_planning_and_exposes_actions(self):
        service = AgentService(domain_pack=AmbiguousTextDomainPack())
        try:
            pending = service.run(
                request="请处理这段内容",
                session_id="m166-ambiguous",
                planner="rule",
                backend="memory",
            )
        finally:
            service.close()

        self.assertEqual(pending["status"], "NEEDS_CLARIFICATION")
        result = pending["result"]
        selection = result["planning"]["workflow_selection"]
        self.assertEqual(selection["state"], "ambiguous")
        self.assertEqual(selection["selected_capability_id"], None)
        self.assertEqual(
            result["selection_interaction"]["state"], "candidate_selection"
        )
        self.assertEqual(
            result["selection_interaction"]["allowed_actions"],
            ["select_capability", "select_workflow", "cancel"],
        )
        self.assertEqual(pending["steps"], [])

    def test_capability_choice_resolves_through_domain_and_reuses_runtime_path(self):
        service = AgentService(domain_pack=AmbiguousTextDomainPack())
        try:
            pending = service.run(
                request="请处理这段内容",
                session_id="m166-ambiguous-resume",
                planner="rule",
                backend="memory",
            )
            completed = service.apply_run_interaction(
                pending["run_id"],
                "select_capability",
                {
                    "capability_id": "text_summary",
                    "require_confirmation": False,
                },
                planner="rule",
                backend="memory",
            )
        finally:
            service.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["result"]["type"], "text_summary_result")
        self.assertEqual(
            completed["result"]["planning"]["workflow_selection"]["source"],
            "explicit_workflow",
        )

    def test_text_sync_and_async_share_core_contract(self):
        with tempfile.TemporaryDirectory(prefix="m166-open-text-") as directory:
            root = Path(directory)
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=ArtifactStore(root / "artifacts"),
                runtime_factory=_text_runtime_factory, domain_id="text",
            )
            try:
                request = "请概括：统一 Runtime 需要可观测、可替换和可恢复。"
                direct = service.run(
                    request=request,
                    session_id="m166-text-sync",
                    planner="rule",
                    backend="memory",
                    export_artifact=True,
                )
                submitted = service.run_async(
                    request=request,
                    session_id="m166-text-async",
                    planner="rule",
                    backend="memory",
                    export_artifact=True,
                    idempotency_key="m166-open-text",
                )
                asynchronous = _wait_for_terminal(service, submitted["run_id"])
            finally:
                service.close()

        self.assertEqual(direct["status"], "COMPLETED")
        self.assertEqual(asynchronous["status"], "COMPLETED")
        self.assertEqual(compare_results([direct, asynchronous]), [])

    def test_gis_sync_and_async_share_core_contract(self):
        with tempfile.TemporaryDirectory(prefix="m166-open-gis-") as directory:
            root = Path(directory)
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=ArtifactStore(root / "artifacts"),
            )
            try:
                request = "查询洪山区道路和水体"
                direct = service.run(
                    request=request,
                    session_id="m166-gis-sync",
                    planner="rule",
                    backend="memory",
                    export_artifact=True,
                )
                submitted = service.run_async(
                    request=request,
                    session_id="m166-gis-async",
                    planner="rule",
                    backend="memory",
                    export_artifact=True,
                    idempotency_key="m166-open-gis",
                )
                asynchronous = _wait_for_terminal(service, submitted["run_id"])
            finally:
                service.close()

        self.assertEqual(direct["status"], "COMPLETED")
        self.assertEqual(asynchronous["status"], "COMPLETED")
        self.assertEqual(compare_results([direct, asynchronous]), [])


if __name__ == "__main__":
    unittest.main()
