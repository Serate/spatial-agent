"""M150-B: production/dev HTTP plan-repair acceptance matrix.

This file owns only the HTTP and persistence acceptance seam.  It uses a
deterministic LLM planner client that emits one invalid dependency plan and
then one valid repaired plan, so the test exercises real Runtime wiring
without a network call or a private model key.

The compact async ``result_evidence`` projection intentionally omits repair
events.  Its lineage count is checked against the full run detail, while the
full sync/async payloads, downloaded artifact, and artifact-only recovery are
checked for the complete repair schema and count.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from agent.artifact_store import ArtifactStore
from evaluation.contract_harness import compare_results
from agent.llm_planner import LLMPlanner
from agent.replanning import ReplanningPolicy
from agent.agent_settings import open_agent_defaults
from agent.network import (
    WebFetchAdapter,
    WebSearchAdapter,
    web_fetch_tool_definition,
    web_search_tool_definition,
)
from agent.runtime import AgentRuntime
from agent.service import AgentService
from agent.tools import ToolRegistry
from domains.text.domain import TEXT_DOMAIN_PACK
from domains.text.provider import TextToolProvider
from serve_api import AgentApiHandler


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "scripts" / "production_acceptance.ps1"
REPLANNING_SCHEMA = "spatial-agent.replanning.v1"
ASYNC_SCHEMA = "spatial-agent.async-result-evidence.v1"


class _RepairClient:
    """Return an invalid dependency once, then a valid plan, per run."""

    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, messages: Any, schema: Any) -> dict[str, Any]:
        del messages, schema
        self.calls += 1
        if self.calls % 2:
            return {
                "goal": "带有无效依赖的摘要计划",
                "steps": [
                    {
                        "id": "summary-text",
                        "tool": "summarize_text",
                        "args": {"text": "M150 repair"},
                        "depends_on": ["missing-step"],
                    }
                ],
                "output": {"type": "text_summary_result"},
            }
        return {
            "goal": "修复后的摘要计划",
            "steps": [
                {
                    "id": "summary-text",
                    "tool": "summarize_text",
                    "args": {"text": "M150 repair"},
                    "depends_on": [],
                }
            ],
            "output": {"type": "text_summary_result"},
        }

    def metrics(self) -> dict[str, Any]:
        return {
            "provider": "offline-repair-replay",
            "status": "success",
            "usage": {"total_tokens": 12},
            "latency_ms": 1.0,
            "attempts": 1,
            "retries": 0,
        }


def _repair_runtime_factory(
    planner: str,
    backend: str,
    *,
    state_store: Any = None,
    conversation_store: Any = None,
    memory: Any = None,
    observability: Any = None,
    **_: Any,
) -> AgentRuntime:
    registry = ToolRegistry.from_provider(TextToolProvider())
    defaults = open_agent_defaults()
    if defaults["web_search_enabled"] and defaults.get("web_mode") != "off":
        if "web_search" not in registry.names:
            registry.register_tool(
                "web_search",
                web_search_tool_definition(),
                WebSearchAdapter.from_settings(defaults).invoke,
            )
        if "web_fetch" not in registry.names:
            registry.register_tool(
                "web_fetch",
                web_fetch_tool_definition(),
                WebFetchAdapter.from_settings(defaults).invoke,
            )
    return AgentRuntime(
        LLMPlanner(_RepairClient(), registry.names),
        registry,
        state_store=state_store,
        conversation_store=conversation_store,
        memory=memory,
        observability=observability,
        replan_policy=ReplanningPolicy(limit=1),
        backend_name=backend,
        planner_name=planner,
        domain_pack=TEXT_DOMAIN_PACK,
    )


def _post(port: int, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
    connection = HTTPConnection("127.0.0.1", port, timeout=8)
    try:
        connection.request(
            "POST",
            path,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        body = json.loads(raw.decode("utf-8")) if "json" in content_type.lower() else raw
        return response.status, body
    finally:
        connection.close()


def _get(port: int, path: str) -> tuple[int, Any]:
    connection = HTTPConnection("127.0.0.1", port, timeout=8)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        body = json.loads(raw.decode("utf-8")) if "json" in content_type.lower() else raw
        return response.status, body
    finally:
        connection.close()


@contextmanager
def _dev_server(service: AgentService, root: Path):
    class RepairHandler(AgentApiHandler):
        pass

    RepairHandler.service = service
    RepairHandler.artifact_root = root
    RepairHandler.geojson_root = root / "geojson"
    server = ThreadingHTTPServer(("127.0.0.1", 0), RepairHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _wait_dev_run(port: int, run_id: str) -> dict[str, Any]:
    for _ in range(80):
        status, payload = _get(
            port,
            "/runs/{}?planner=openai&backend=memory".format(run_id),
        )
        if status == 200 and payload.get("status") not in {
            "CREATED",
            "PLANNING",
            "EXECUTING",
            "QUEUED",
        }:
            return payload
        time.sleep(0.025)
    raise AssertionError("async run did not reach a terminal state")


def _assert_repair_lineage(testcase: unittest.TestCase, payload: dict[str, Any]) -> int:
    result = payload.get("result")
    testcase.assertIsInstance(result, dict)
    repair = result.get("replanning")
    testcase.assertIsInstance(repair, dict)
    testcase.assertEqual(repair.get("schema_version"), REPLANNING_SCHEMA)
    events = repair.get("events")
    testcase.assertIsInstance(events, list)
    testcase.assertEqual(repair.get("count"), len(events))
    testcase.assertTrue(repair.get("available"))
    testcase.assertEqual(len(events), 1)
    event = events[0]
    testcase.assertEqual(event.get("phase"), "planning")
    testcase.assertEqual(event.get("failed_step_id"), "plan-validation")
    testcase.assertEqual(event.get("failed_tool"), "planner")
    testcase.assertIsInstance(event.get("replanned_step_ids"), list)

    lineage = result.get("lineage")
    testcase.assertIsInstance(lineage, dict)
    repair_lineage = lineage.get("replanning")
    testcase.assertIsInstance(repair_lineage, dict)
    testcase.assertEqual(repair_lineage.get("count"), repair.get("count"))
    testcase.assertTrue(repair_lineage.get("available"))

    if "replan_events" in payload:
        testcase.assertEqual(len(payload["replan_events"]), len(events))
    return int(repair["count"])


def _assert_async_lineage(
    testcase: unittest.TestCase,
    observation: dict[str, Any],
    expected_count: int,
) -> None:
    evidence = observation.get("result_evidence")
    testcase.assertIsInstance(evidence, dict)
    testcase.assertEqual(evidence.get("schema_version"), ASYNC_SCHEMA)
    testcase.assertIn(evidence.get("state"), {"success", "degraded"})
    lineage = observation.get("lineage")
    testcase.assertIsInstance(lineage, dict)
    repair_lineage = lineage.get("replanning")
    testcase.assertIsInstance(repair_lineage, dict)
    testcase.assertEqual(repair_lineage.get("count"), expected_count)


class M150ProductionRepairTests(unittest.TestCase):
    def _run_offline_acceptance(self, payload: dict[str, Any]):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            self.skipTest("PowerShell is unavailable; production acceptance skipped")
        with tempfile.TemporaryDirectory(prefix="m150-contract-") as directory:
            payload_path = Path(directory) / "payload.json"
            payload_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            return subprocess.run(
                [
                    shell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ACCEPTANCE),
                    "-ContractPayloadPath",
                    str(payload_path),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )

    def test_dev_http_sync_async_artifact_and_recovery_retain_repair_lineage(self):
        with tempfile.TemporaryDirectory(prefix="m150-dev-") as directory:
            root = Path(directory)
            store = ArtifactStore(root)
            service = AgentService(
                artifact_store=store,
                state_db_path=str(root / "state.db"),
                runtime_factory=_repair_runtime_factory, domain_id="text",
            )
            try:
                with _dev_server(service, root) as port:
                    request = "请摘要 M150 repair"
                    status, sync = _post(
                        port,
                        "/runs",
                        {
                            "request": request,
                            "planner": "openai",
                            "backend": "memory",
                            "session_id": "m150-dev-sync",
                            "export_artifact": True,
                        },
                    )
                    self.assertEqual(status, 200, sync)
                    self.assertEqual(sync.get("status"), "COMPLETED")
                    sync_count = _assert_repair_lineage(self, sync)
                    self.assertEqual(sync_count, 1)
                    artifact_name = Path(sync["artifact_ref"]).name
                    status, sync_artifact_bytes = _get(
                        port, "/artifacts/runs/" + artifact_name
                    )
                    self.assertEqual(status, 200)
                    sync_artifact = (
                        sync_artifact_bytes
                        if isinstance(sync_artifact_bytes, dict)
                        else json.loads(sync_artifact_bytes.decode("utf-8"))
                    )
                    self.assertEqual(_assert_repair_lineage(self, sync_artifact), sync_count)
                    self.assertEqual(compare_results([sync, sync_artifact]), [])

                    status, queued = _post(
                        port,
                        "/runs/async",
                        {
                            "request": request,
                            "planner": "openai",
                            "backend": "memory",
                            "session_id": "m150-dev-async",
                            "idempotency_key": "m150-dev-repair",
                            "export_artifact": True,
                        },
                    )
                    self.assertEqual(status, 200, queued)
                    final = _wait_dev_run(port, queued["run_id"])
                    self.assertEqual(final.get("status"), "COMPLETED")
                    async_count = _assert_repair_lineage(self, final)
                    self.assertEqual(async_count, sync_count)
                    status, observation = _get(
                        port, "/runs/{}/async".format(queued["run_id"])
                    )
                    self.assertEqual(status, 200, observation)
                    _assert_async_lineage(self, observation, async_count)

                    async_artifact_name = Path(final["artifact_ref"]).name
                    status, async_artifact_bytes = _get(
                        port, "/artifacts/runs/" + async_artifact_name
                    )
                    self.assertEqual(status, 200)
                    async_artifact = (
                        async_artifact_bytes
                        if isinstance(async_artifact_bytes, dict)
                        else json.loads(async_artifact_bytes.decode("utf-8"))
                    )
                    self.assertEqual(
                        _assert_repair_lineage(self, async_artifact), async_count
                    )
                    self.assertEqual(compare_results([final, async_artifact]), [])

                    for surface, payload in (
                        ("sync", sync),
                        ("sync-artifact", sync_artifact),
                        ("async", final),
                        ("async-artifact", async_artifact),
                    ):
                        with self.subTest(surface=surface):
                            accepted = self._run_offline_acceptance(payload)
                            self.assertEqual(
                                accepted.returncode,
                                0,
                                accepted.stdout + accepted.stderr,
                            )

                service.close()
                recovered_service = AgentService(
                    artifact_store=store,
                    state_db_path=str(root / "state.db"),
                    runtime_factory=_repair_runtime_factory, domain_id="text",
                )
                try:
                    recovered = recovered_service.get_run(
                        queued["run_id"], planner="openai", backend="memory"
                    )
                    self.assertEqual(
                        _assert_repair_lineage(self, recovered), async_count
                    )
                    recovered_accepted = self._run_offline_acceptance(recovered)
                    self.assertEqual(
                        recovered_accepted.returncode,
                        0,
                        recovered_accepted.stdout + recovered_accepted.stderr,
                    )
                    recovered_observation = recovered_service.get_async_observability(
                        queued["run_id"]
                    )
                    _assert_async_lineage(
                        self, recovered_observation, async_count
                    )
                finally:
                    recovered_service.close()

                # Also verify the artifact-only detail boundary.  Its
                # compact async evidence is intentionally unavailable for a
                # missing SQLite job row, but the full recovered result must
                # still retain the repair schema and lineage count.
                artifact_only_service = AgentService(
                    artifact_store=store,
                    runtime_factory=_repair_runtime_factory, domain_id="text",
                )
                try:
                    artifact_only = artifact_only_service.get_run(
                        queued["run_id"], planner="openai", backend="memory"
                    )
                    self.assertEqual(
                        _assert_repair_lineage(self, artifact_only), async_count
                    )
                finally:
                    artifact_only_service.close()
            finally:
                # The explicit close above is needed before artifact-only
                # recovery; this remains safe if an assertion failed earlier.
                service.close()

    def test_production_gate_rejects_repair_count_drift(self):
        with tempfile.TemporaryDirectory(prefix="m150-negative-") as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_repair_runtime_factory, domain_id="text",
            )
            try:
                payload = service.run(
                    "请摘要 M150 repair",
                    planner="openai",
                    backend="memory",
                    export_artifact=True,
                )
            finally:
                service.close()
        self.assertEqual(_assert_repair_lineage(self, payload), 1)
        changed = copy.deepcopy(payload)
        changed["result"]["replanning"]["count"] = 0
        rejected = self._run_offline_acceptance(changed)
        self.assertNotEqual(rejected.returncode, 0, rejected.stdout)

    def test_fastapi_production_matrix_or_explicit_dependency_skip(self):
        try:
            import production_api
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                self.skipTest("FastAPI is not installed; production matrix skipped")
            raise
        try:
            from fastapi.testclient import TestClient
        except (ModuleNotFoundError, RuntimeError) as exc:
            self.skipTest(
                "FastAPI test client dependency is unavailable: {}".format(
                    getattr(exc, "name", str(exc))
                )
            )

        with tempfile.TemporaryDirectory(prefix="m150-fastapi-") as directory:
            root = Path(directory)
            replacement = AgentService(
                artifact_store=ArtifactStore(root),
                runtime_factory=_repair_runtime_factory, domain_id="text",
            )
            old_service = production_api.service
            old_artifact_root = production_api.ARTIFACT_ROOT
            old_geojson_root = production_api.GEOJSON_ROOT
            try:
                production_api.service = replacement
                production_api.ARTIFACT_ROOT = root
                production_api.GEOJSON_ROOT = root / "geojson"
                with TestClient(production_api.app) as client:
                    response = client.post(
                        "/runs",
                        json={
                            "request": "请摘要 M150 FastAPI repair",
                            "planner": "openai",
                            "backend": "memory",
                            "session_id": "m150-fastapi-sync",
                            "export_artifact": True,
                        },
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    sync = response.json()
                    sync_count = _assert_repair_lineage(self, sync)
                    artifact_name = Path(sync["artifact_ref"]).name
                    artifact_response = client.get(
                        "/artifacts/runs/" + artifact_name
                    )
                    self.assertEqual(artifact_response.status_code, 200)
                    artifact = artifact_response.json()
                    self.assertEqual(_assert_repair_lineage(self, artifact), sync_count)

                    accepted = self._run_offline_acceptance(sync)
                    self.assertEqual(
                        accepted.returncode,
                        0,
                        accepted.stdout + accepted.stderr,
                    )

                    queued_response = client.post(
                        "/runs/async",
                        json={
                            "request": "请摘要 M150 FastAPI async repair",
                            "planner": "openai",
                            "backend": "memory",
                            "session_id": "m150-fastapi-async",
                            "idempotency_key": "m150-fastapi-repair",
                            "export_artifact": True,
                        },
                    )
                    self.assertEqual(
                        queued_response.status_code, 200, queued_response.text
                    )
                    queued = queued_response.json()
                    final = None
                    for _ in range(80):
                        candidate_response = client.get(
                            "/runs/{}?planner=openai&backend=memory".format(
                                queued["run_id"]
                            )
                        )
                        if candidate_response.status_code == 200:
                            candidate = candidate_response.json()
                            if candidate.get("status") not in {
                                "CREATED",
                                "PLANNING",
                                "EXECUTING",
                                "QUEUED",
                            }:
                                final = candidate
                                break
                        time.sleep(0.025)
                    self.assertIsNotNone(final, "FastAPI async run did not finish")
                    self.assertEqual(final.get("status"), "COMPLETED")
                    async_count = _assert_repair_lineage(self, final)
                    self.assertEqual(async_count, sync_count)
                    observation_response = client.get(
                        "/runs/{}/async".format(queued["run_id"])
                    )
                    self.assertEqual(
                        observation_response.status_code,
                        200,
                        observation_response.text,
                    )
                    _assert_async_lineage(
                        self, observation_response.json(), async_count
                    )
                    async_artifact_name = Path(final["artifact_ref"]).name
                    async_artifact_response = client.get(
                        "/artifacts/runs/" + async_artifact_name
                    )
                    self.assertEqual(async_artifact_response.status_code, 200)
                    async_artifact = async_artifact_response.json()
                    self.assertEqual(
                        _assert_repair_lineage(self, async_artifact), async_count
                    )
                    accepted_async = self._run_offline_acceptance(final)
                    self.assertEqual(
                        accepted_async.returncode,
                        0,
                        accepted_async.stdout + accepted_async.stderr,
                    )
            finally:
                production_api.service = old_service
                production_api.ARTIFACT_ROOT = old_artifact_root
                production_api.GEOJSON_ROOT = old_geojson_root
                replacement.close()


if __name__ == "__main__":
    unittest.main()
