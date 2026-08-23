"""M220-B2: Text Domain exercises the shared composed lifecycle."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.component_evidence import (
    normalize_workflow_component_evidence,
    project_workflow_component_evidence,
)
from agent.evidence_revalidation import build_evidence_revalidation
from agent.service import AgentService
from agent.transition_evidence import build_transition_evidence
from domains.text.domain import TEXT_DOMAIN_PACK
from evaluation.contract_harness import compare_results
from serve_api import AgentApiHandler


def _workflow() -> dict:
    text = "  Agent Runtime 需要统一的计划、工具和证据契约。  "
    return {
        "components": [
            {
                "component_id": "normalize",
                "template_id": "text_normalize",
                "constraints": {"text": text},
            },
            {
                "component_id": "summary",
                "template_id": "text_summary",
                "constraints": {"text": text},
                "depends_on_components": ["normalize"],
            },
            {
                "component_id": "stats",
                "template_id": "text_stats",
                "constraints": {"text": text},
                "depends_on_components": ["normalize"],
            },
        ]
    }


def _request_json(port: int, method: str, path: str, payload: dict | None = None) -> dict:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    value = json.loads(response.read().decode("utf-8"))
    connection.close()
    if response.status >= 400:
        raise AssertionError((response.status, value))
    return value


def _wait_for_terminal(service: AgentService, run_id: str) -> dict:
    for _ in range(300):
        value = service.get_run(run_id)
        if value.get("status") not in {"QUEUED", "PLANNING", "EXECUTING"}:
            return value
        time.sleep(0.01)
    raise AssertionError("text composition did not reach a terminal state")


class M220ComposedCrossDomainTests(unittest.TestCase):
    def test_component_evidence_projects_quality_dimensions_and_revalidation(self):
        revalidation = build_evidence_revalidation(
            build_transition_evidence(
                {"data_readiness": "ready"},
                {"data_readiness": "not_ready", "coverage_status": "stale"},
            )
        )
        projected = project_workflow_component_evidence(
            {
                "components": [
                    {
                        "component_id": "source",
                        "template_id": "text_summary",
                        "evidence_summary": {
                            "schema_version": "spatial-agent.capability-evidence.v1",
                            "status": "ready",
                            "readiness": {"status": "ready", "required": True},
                            "coverage": {
                                "status": "ready",
                                "dataset_count": 1,
                                "covered_dataset_count": 1,
                            },
                            "provenance": {"status": "ready", "source_count": 1},
                            "freshness": {"status": "stale", "age_seconds": 7200},
                            "conflicts": {"status": "detected", "count": 1},
                            "evidence_revalidation": revalidation,
                        },
                    }
                ]
            }
        )

        component = projected["components"][0]
        self.assertEqual(component["state"], "blocked")
        self.assertEqual(component["freshness"]["status"], "stale")
        self.assertEqual(component["conflicts"]["status"], "detected")
        self.assertEqual(component["evidence_revalidation"]["state"], "blocked")
        self.assertEqual(
            normalize_workflow_component_evidence(projected),
            projected,
        )

    def test_text_composition_survives_http_preview_run_and_artifact(self):
        with tempfile.TemporaryDirectory(prefix="m220-text-http-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
                domain_pack=TEXT_DOMAIN_PACK,
            )

            class Handler(AgentApiHandler):
                pass

            Handler.service = service
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {
                    "request": "组合处理这段文本",
                    "session_id": "m220-text-http",
                    "planner": "rule",
                    "backend": "memory",
                    "workflow": _workflow(),
                    "export_artifact": True,
                }
                preview = _request_json(server.server_address[1], "POST", "/runs/preview", payload)
                payload["preview_fingerprint"] = preview["plan_identity"]["fingerprint"]
                completed = _request_json(server.server_address[1], "POST", "/runs", payload)
                detail = _request_json(
                    server.server_address[1],
                    "GET",
                    "/runs/" + completed["run_id"],
                )
                artifact = store.read_run(completed["run_id"], domain_id="text")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["result"]["type"], "text_analysis_result")
        self.assertIn("组合文本分析", completed["answer"])
        expected_components = ["normalize", "summary", "stats"]
        expected_templates = ["text_normalize", "text_summary", "text_stats"]
        for value in (preview, completed, detail, artifact):
            selection = value["plan_evidence"]["workflow_selection"]
            self.assertEqual(selection["workflow_component_ids"], expected_components)
            self.assertEqual(selection["workflow_component_template_ids"], expected_templates)
            identity = value.get("plan_identity") or value["plan_evidence"]["plan_identity"]
            self.assertEqual(identity, preview["plan_identity"])
        self.assertEqual(compare_results([completed, detail, artifact]), [])

    def test_text_composition_async_sqlite_restart_keeps_policy_and_evidence(self):
        with tempfile.TemporaryDirectory(prefix="m220-text-async-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            first = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
                domain_pack=TEXT_DOMAIN_PACK,
            )
            try:
                submitted = first.run_async(
                    request="组合处理这段文本",
                    session_id="m220-text-async",
                    planner="rule",
                    backend="memory",
                    workflow=_workflow(),
                    export_artifact=True,
                    idempotency_key="m220-text-composition",
                )
                completed = _wait_for_terminal(first, submitted["run_id"])
            finally:
                first.close()

            second = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
                domain_pack=TEXT_DOMAIN_PACK,
            )
            try:
                recovered = second.get_run(submitted["run_id"])
                artifact = store.read_run(submitted["run_id"], domain_id="text")
            finally:
                second.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(recovered["status"], "COMPLETED")
        self.assertEqual(recovered["result"]["type"], "text_analysis_result")
        selection = completed["result"]["planning"]["workflow_selection"]
        self.assertEqual(
            selection["workflow_component_evidence"]["summary"]["component_count"],
            3,
        )
        self.assertEqual(
            selection["workflow_component_evidence"]["fingerprint"],
            recovered["result"]["planning"]["workflow_selection"][
                "workflow_component_evidence"
            ]["fingerprint"],
        )
        self.assertEqual(
            completed["result"]["planning"]["plan_policy"]["policy_id"],
            "text.workflow.composition",
        )
        self.assertEqual(
            completed["result"]["planning"]["workflow_selection"],
            recovered["result"]["planning"]["workflow_selection"],
        )
        self.assertEqual(
            completed["result"]["evidence_registry"],
            artifact["evidence_registry"],
        )
        self.assertIn(
            "workflow_component_evidence",
            [
                item["id"]
                for item in completed["result"]["evidence_registry"]["entries"]
            ],
        )


if __name__ == "__main__":
    unittest.main()
