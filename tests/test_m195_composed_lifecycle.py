"""M195-C: composed workflow evidence survives lifecycle recovery seams."""

from __future__ import annotations

import json
import threading
import tempfile
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Optional

from agent.artifact_store import ArtifactStore
from agent.errors import ToolError
from agent.replanning import ReplanningPolicy
from agent.runtime import AgentRuntime
from agent.service import AgentService
from agent.tool_provider import NativeToolProvider
from agent.tools import ToolRegistry
from domains.gis.domain import GIS_DOMAIN_PACK
from serve_api import AgentApiHandler


ROOT = Path(__file__).parents[1]


def _workflow() -> dict[str, Any]:
    return {
        "components": [
            {
                "component_id": "boundary",
                "template_id": "admin_boundary_query",
                "constraints": {"admin_name": "洪山区"},
                "evidence_summary": {
                    "schema_version": "spatial-agent.capability-evidence.v1",
                    "status": "ready",
                    "readiness": {"status": "ready", "required": True},
                    "coverage": {"status": "ready", "dataset_count": 1},
                    "alignment": {"status": "ready"},
                    "provenance": {"status": "ready", "source_count": 1},
                },
            },
            {
                "component_id": "dem",
                "template_id": "raster_metadata",
                "constraints": {"dataset": "dem"},
                "depends_on_components": ["boundary"],
                "evidence_summary": {
                    "schema_version": "spatial-agent.capability-evidence.v1",
                    "status": "degraded",
                    "readiness": {"status": "degraded", "required": True},
                    "coverage": {
                        "status": "ready",
                        "dataset_count": 1,
                        "covered_dataset_count": 1,
                    },
                    "alignment": {"status": "unknown"},
                    "provenance": {"status": "ready", "source_count": 1},
                    "missing_reasons": ["等待真实 DEM 对齐检查"],
                },
            },
        ]
    }


class _SlowPlanner:
    def __init__(self, delay_seconds: float = 0.08):
        self._delegate = GIS_DOMAIN_PACK.rule_planner()
        self._delay_seconds = delay_seconds

    def plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]] = None,
        context: Optional[Mapping[str, Any]] = None,
    ):
        time.sleep(self._delay_seconds)
        return self._delegate.plan(request, workflow=workflow, context=context)


def _slow_runtime_factory(planner: str, backend: str, **kwargs: Any) -> AgentRuntime:
    provider = GIS_DOMAIN_PACK.tool_provider(backend_name=backend, root=ROOT)
    return AgentRuntime(
        _SlowPlanner(),
        ToolRegistry.from_provider(provider),
        domain_pack=GIS_DOMAIN_PACK,
        planner_name=planner,
        backend_name=backend,
        max_retries=0,
        **kwargs,
    )


class _FailOnceAdapter:
    def __init__(self, provider: Any):
        self._provider = provider
        self._failed = False

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "get_raster_metadata" and not self._failed:
            self._failed = True
            raise ToolError(
                "temporary raster provider failure",
                category="provider",
                code="temporary_provider_failure",
                retryable=False,
            )
        return self._provider.invoke(name, arguments)


def _flaky_runtime_factory(planner: str, backend: str, **kwargs: Any) -> AgentRuntime:
    provider = GIS_DOMAIN_PACK.tool_provider(backend_name=backend, root=ROOT)
    flaky_provider = NativeToolProvider(
        provider.definitions(),
        _FailOnceAdapter(provider),
    )
    return AgentRuntime(
        GIS_DOMAIN_PACK.rule_planner(),
        ToolRegistry.from_provider(flaky_provider),
        domain_pack=GIS_DOMAIN_PACK,
        planner_name=planner,
        backend_name=backend,
        max_retries=0,
        replan_policy=ReplanningPolicy(limit=0),
        **kwargs,
    )


def _wait_for_terminal(service: AgentService, run_id: str, timeout: float = 5.0) -> dict[str, Any]:
    terminal = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT", "REJECTED", "NEEDS_CLARIFICATION"}
    deadline = time.monotonic() + timeout
    snapshot = None
    while time.monotonic() < deadline:
        snapshot = service.get_run(run_id)
        if snapshot.get("status") in terminal:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("composed lifecycle run did not reach terminal state: {!r}".format(snapshot))


def _components(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    plan_evidence = payload.get("plan_evidence")
    selection = (
        plan_evidence.get("workflow_selection", {})
        if isinstance(plan_evidence, Mapping)
        else {}
    )
    return selection.get("workflow_components", [])


def _async_components(observation: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence = observation.get("result_evidence", {})
    projection = evidence.get("evidence_projection", {})
    selection = projection.get("selection", {}).get("workflow_selection", {})
    return selection.get("workflow_components", [])


def _request_json(port: int, method: str, path: str, payload: Any = None) -> dict[str, Any]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()
    if response.status >= 400:
        raise AssertionError("HTTP {}: {}".format(response.status, data))
    return data


class M195ComposedLifecycleTests(unittest.TestCase):
    def test_confirmation_cancel_keeps_composed_evidence_and_receipt(self):
        with tempfile.TemporaryDirectory(prefix="m195-composed-cancel-") as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=artifacts,
                domain_pack=GIS_DOMAIN_PACK,
            )
            try:
                waiting = service.run(
                    "组合查询洪山区边界和 DEM 元数据",
                    session_id="m195-composed-cancel",
                    planner="rule",
                    backend="memory",
                    workflow=_workflow(),
                    require_confirmation=True,
                    export_artifact=True,
                )
                cancelled = service.cancel(
                    waiting["run_id"],
                    idempotency_key="m195-composed-cancel-action",
                )
                detail = service.get_run(waiting["run_id"])
                artifact = artifacts.read_run(waiting["run_id"], domain_id="gis")
            finally:
                service.close()

        expected = _components(waiting)
        self.assertEqual(waiting["status"], "WAITING_FOR_DECISION")
        self.assertEqual(cancelled["current_status"], "CANCELLED")
        self.assertEqual(detail["status"], "CANCELLED")
        self.assertEqual(_components(detail), expected)
        self.assertEqual(_components(artifact), expected)
        self.assertEqual(
            cancelled["action_receipt"]["action_id"],
            "cancel",
        )
        self.assertEqual(
            detail["action_receipt"]["action_id"],
            "cancel",
        )

    def test_retry_preserves_composed_evidence_and_writes_lineage(self):
        with tempfile.TemporaryDirectory(prefix="m195-composed-retry-") as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=artifacts,
                runtime_factory=_flaky_runtime_factory,
            )
            try:
                failed = service.run(
                    "组合查询洪山区边界和 DEM 元数据",
                    session_id="m195-composed-retry",
                    planner="rule",
                    backend="memory",
                    workflow=_workflow(),
                    export_artifact=True,
                )
                retried = service.retry(
                    failed["run_id"],
                    idempotency_key="m195-composed-retry-action",
                )
                detail = service.get_run(failed["run_id"])
                artifact = artifacts.read_run(failed["run_id"], domain_id="gis")
            finally:
                service.close()

        expected = _components(failed)
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(retried["status"], "COMPLETED")
        self.assertEqual(_components(retried), expected)
        self.assertEqual(_components(detail), _components(retried))
        self.assertEqual(_components(artifact), _components(retried))
        self.assertEqual(retried["action_receipt"]["action_id"], "retry")
        self.assertGreaterEqual(
            retried["result"]["lifecycle"]["lineage"]["retry_count"],
            1,
        )
        self.assertEqual(
            retried["action_receipt"]["transition_lineage"]["events"][-1]["action_id"],
            "retry",
        )

    def test_two_services_share_one_composed_async_run_and_evidence(self):
        with tempfile.TemporaryDirectory(prefix="m195-composed-workers-") as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            first = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=artifacts,
                domain_pack=GIS_DOMAIN_PACK,
            )
            second = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=artifacts,
                domain_pack=GIS_DOMAIN_PACK,
            )
            try:
                request = {
                    "request": "组合查询洪山区边界和 DEM 元数据",
                    "session_id": "m195-composed-workers",
                    "planner": "rule",
                    "backend": "memory",
                    "workflow": _workflow(),
                    "export_artifact": True,
                    "idempotency_key": "m195-composed-workers-key",
                }
                first_submission = first.run_async(**request)
                second_submission = second.run_async(**request)
                completed = _wait_for_terminal(second, first_submission["run_id"])
                observation = second.get_async_observability(first_submission["run_id"])
                artifact = artifacts.read_run(first_submission["run_id"], domain_id="gis")
            finally:
                first.close()
                second.close()

        self.assertEqual(first_submission["run_id"], second_submission["run_id"])
        self.assertTrue(
            first_submission["idempotent"] != second_submission["idempotent"]
            or first_submission["reused"] != second_submission["reused"]
        )
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(_components(completed), _components(artifact))
        self.assertEqual(_async_components(observation), _components(artifact))

    def test_http_preview_run_detail_and_artifact_keep_component_evidence(self):
        with tempfile.TemporaryDirectory(prefix="m195-composed-http-") as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=artifacts,
                domain_pack=GIS_DOMAIN_PACK,
            )

            class Handler(AgentApiHandler):
                pass

            Handler.service = service
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {
                    "request": "组合查询洪山区边界和 DEM 元数据",
                    "session_id": "m195-composed-http",
                    "planner": "rule",
                    "backend": "memory",
                    "workflow": _workflow(),
                    "export_artifact": True,
                }
                preview = _request_json(
                    server.server_address[1], "POST", "/runs/preview", payload
                )
                payload["preview_fingerprint"] = preview["plan_identity"]["fingerprint"]
                completed = _request_json(
                    server.server_address[1], "POST", "/runs", payload
                )
                detail = _request_json(
                    server.server_address[1],
                    "GET",
                    "/runs/" + completed["run_id"],
                )
                artifact = artifacts.read_run(completed["run_id"], domain_id="gis")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

        expected = _components(preview)
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(_components(completed), expected)
        self.assertEqual(_components(detail), expected)
        self.assertEqual(_components(artifact), expected)

    def test_timeout_preserves_component_evidence_across_async_artifact_restart(self):
        with tempfile.TemporaryDirectory(prefix="m195-composed-timeout-") as directory:
            root = Path(directory)
            artifacts = ArtifactStore(root / "artifacts")
            first = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=artifacts,
                runtime_factory=_slow_runtime_factory,
            )
            submitted = first.run_async(
                request="组合查询洪山区边界和 DEM 元数据",
                session_id="m195-composed-timeout",
                planner="rule",
                backend="memory",
                workflow=_workflow(),
                timeout_seconds=0.01,
                export_artifact=True,
                idempotency_key="m195-composed-timeout-key",
            )
            try:
                completed = _wait_for_terminal(first, submitted["run_id"])
                live_observation = first.get_async_observability(submitted["run_id"])
            finally:
                first.close()

            artifact = artifacts.read_run(submitted["run_id"], domain_id="gis")
            restarted = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=artifacts,
                domain_pack=GIS_DOMAIN_PACK,
            )
            try:
                recovered = restarted.get_run(submitted["run_id"])
                recovered_observation = restarted.get_async_observability(
                    submitted["run_id"]
                )
            finally:
                restarted.close()

        self.assertEqual(completed["status"], "TIMED_OUT")
        expected = _components(artifact)
        self.assertEqual([item["component_id"] for item in expected], ["boundary", "dem"])
        self.assertEqual(expected[1]["evidence_summary"]["status"], "degraded")
        self.assertEqual(_components(completed), expected)
        self.assertEqual(_components(recovered), expected)
        self.assertEqual(_async_components(live_observation), expected)
        self.assertEqual(_async_components(recovered_observation), expected)


if __name__ == "__main__":
    unittest.main()
