"""M308 Docker acceptance for one prepared 3+ component plan across entries.

The planner is a bounded replay.  The Domain Host, real local data services,
TaskPlan bridge, execution binding, SQLite state and artifact store remain
real.  Output is a small identity receipt and never includes raw results.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from agent.application.composite import CompositeApplication
from agent.application.composite_planning import (
    CompositeCapabilityProjector,
    CompositePlanningApplication,
)
from agent.application.composite_runs import CompositeRunApplication
from agent.application.http import HTTPApplication
from agent.artifact_store import ArtifactStore
from agent.composite_view import build_composite_view_projection
from agent.composite_planner import ReplayCompositePlanner
from agent.domain_runtime_host import DomainRuntimeHost
from scripts.m308_real_composition_acceptance import _payload


REQUEST = "请组合分析洪山区空间总览、经济指标目录和区域指标目录"
DOMAINS = ["gis", "economic", "indicators"]


def _component_states(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "component_id": str(item.get("component_id") or "")[:48],
            "state": str(item.get("state") or "")[:24],
            "status": str(item.get("status") or "")[:32],
        }
        for item in value[:8]
        if isinstance(item, Mapping)
    ]


def _identity(value: Mapping[str, Any]) -> dict[str, Any]:
    result = value.get("result") if isinstance(value.get("result"), Mapping) else {}
    view = value.get("view") if isinstance(value.get("view"), Mapping) else {}
    answer = view.get("answer") if isinstance(view.get("answer"), Mapping) else {}
    request = result.get("composite", {}).get("request", {}) if isinstance(result.get("composite"), Mapping) else {}
    view_components = [
        item
        for item in (view.get("sections") or [])
        if isinstance(item, Mapping) and item.get("kind") == "component"
    ]
    component_states = _component_states(view_components)
    if not component_states:
        component_states = _component_states(
            value.get("components") or result.get("components")
        )
    return {
        "status": str(value.get("status") or "")[:32],
        "result_type": str(result.get("type") or "")[:96],
        "state": str(result.get("composite", {}).get("state") or "")[:24]
        if isinstance(result.get("composite"), Mapping)
        else "",
        "data_kinds": list(view.get("data_kinds") or [])[:8],
        "component_states": component_states,
        "request_fingerprint": str(
            value.get("request_fingerprint") or request.get("fingerprint") or ""
        )[:128],
        "binding_fingerprint": str(
            (value.get("execution_binding") or {}).get("binding_fingerprint")
            if isinstance(value.get("execution_binding"), Mapping)
            else request.get("execution_binding", {}).get("binding_fingerprint")
            if isinstance(request.get("execution_binding"), Mapping)
            else ""
        )[:128],
        "answer": dict(answer),
    }


def _evidence_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    binding = value.get("execution_binding")
    answer = value.get("answer_generation")
    return {
        "binding_fingerprint": str(binding.get("binding_fingerprint") or "")[:128]
        if isinstance(binding, Mapping)
        else "",
        "evidence_registry_available": bool(
            (value.get("evidence_registry") or {}).get("available")
        ),
        "evidence_recovery_available": bool(
            (value.get("evidence_recovery") or {}).get("available")
        ),
        "answer_generation_status": str(
            answer.get("status") or "unavailable"
        )[:32]
        if isinstance(answer, Mapping)
        else "unavailable",
    }


def _wait_for_terminal(application: CompositeRunApplication, run_id: str) -> Mapping[str, Any]:
    deadline = time.time() + 90
    while time.time() < deadline:
        observation = application.get_observability(run_id)
        if str(observation.get("status") or "").upper() in {
            "COMPLETED",
            "PARTIAL",
            "FAILED",
            "BLOCKED",
            "CANCELLED",
            "TIMED_OUT",
        }:
            return application.get_run(run_id)
        time.sleep(0.1)
    return {"status": "TIMED_OUT", "error_code": "m308_cross_entry_timeout"}


def _same(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return _identity(left) == _identity(right)


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="spatial-agent-m308-") as directory:
        root = Path(directory)
        database = str(root / "runs.db")
        artifact_root = str(root / "artifacts")
        host = DomainRuntimeHost()
        host.start()
        first = CompositeRunApplication(
            coordinator=CompositeApplication(host=host, require_execution_binding=True),
            state_db_path=database,
            artifact_root=artifact_root,
            worker_count=1,
        )
        try:
            planning = CompositePlanningApplication(
                host=host,
                projector=CompositeCapabilityProjector(host),
                planner=ReplayCompositePlanner(_payload()),
                composite_runs=first,
            ).prepare(
                REQUEST,
                planner_name="rule",
                backend="local",
                domain_ids=DOMAINS,
            )
            if planning.get("status") != "PLANNED":
                return {
                    "status": "PLANNING_FAILED",
                    "error_code": planning.get("error_code"),
                }
            canonical = planning.get("request")
            binding = getattr(planning, "execution_binding", None)
            if not isinstance(canonical, Mapping) or not isinstance(binding, Mapping):
                return {"status": "PLANNING_FAILED", "error_code": "binding_missing"}
            evidence = planning.get("planner_evidence")

            sync = first.run_with_planning(
                canonical,
                session_id="m308-cross-sync",
                export_artifact=True,
                planner_evidence=evidence if isinstance(evidence, Mapping) else None,
                execution_binding=binding,
            )
            submitted = first.submit_async_with_planning(
                canonical,
                session_id="m308-cross-async",
                idempotency_key="m308-cross-async-1",
                export_artifact=True,
                planner_evidence=evidence if isinstance(evidence, Mapping) else None,
                execution_binding=binding,
            )
            async_detail = _wait_for_terminal(first, str(submitted.get("run_id") or ""))
            http = HTTPApplication(object(), composite=first)
            sync_view = http.read("composite_view", resource_id=str(sync.get("run_id") or ""))
            sync_evidence = http.read("composite_evidence", resource_id=str(sync.get("run_id") or ""))
            artifact_store = ArtifactStore(artifact_root, legacy_domain_id="composite")
            artifact = artifact_store.read_run(str(sync.get("run_id") or ""), domain_id="composite") or {}
            artifact_result = artifact.get("result") if isinstance(artifact, Mapping) else {}
            artifact_view = build_composite_view_projection(artifact_result) if isinstance(artifact_result, Mapping) else {}
            artifact_response = {
                "status": artifact.get("status"),
                "run_id": artifact.get("run_id"),
                "result": artifact_result,
                "view": artifact_view,
                "components": artifact_result.get("components") if isinstance(artifact_result, Mapping) else [],
            }
            sync_identity = _identity(sync)
            async_identity = _identity(async_detail)
            http_identity = _identity({"status": sync.get("status"), "result": sync.get("result"), "view": sync_view, "components": sync.get("components"), "request_fingerprint": sync.get("request_fingerprint"), "execution_binding": sync.get("execution_binding")})
            artifact_identity = _identity(artifact_response)
            evidence_identity = _evidence_identity(sync_evidence)
            artifact_evidence = _evidence_identity({
                "execution_binding": artifact_result.get("composite", {}).get("request", {}).get("execution_binding")
                if isinstance(artifact_result, Mapping) and isinstance(artifact_result.get("composite"), Mapping)
                else None,
                "evidence_registry": artifact_result.get("evidence_registry") if isinstance(artifact_result, Mapping) else None,
                "evidence_recovery": artifact_result.get("evidence_recovery") if isinstance(artifact_result, Mapping) else None,
                "answer_generation": artifact_result.get("answer_generation_evidence") if isinstance(artifact_result, Mapping) else None,
            })
            first.close()
            restarted = CompositeRunApplication(
                coordinator=CompositeApplication(host=host, require_execution_binding=True),
                state_db_path=database,
                artifact_root=artifact_root,
                worker_count=1,
            )
            try:
                restart_view = restarted.get_view(str(sync.get("run_id") or ""))
                restart_evidence = restarted.get_evidence(str(sync.get("run_id") or ""))
            finally:
                restarted.close()
            return {
                "status": "COMPLETED" if sync_identity["status"] == "COMPLETED" and async_identity["status"] == "COMPLETED" else "FAILED",
                "planning": {"status": planning.get("status"), "component_count": len(planning.get("components") or [])},
                "sync": sync_identity,
                "async": async_identity,
                "cross_entry": {
                    "sync_async_same": _same(sync, async_detail),
                    "http_view_same": http_identity == sync_identity,
                    "artifact_view_same": artifact_identity == sync_identity,
                    "evidence_same": evidence_identity == artifact_evidence,
                    "restart_view_same": _identity({
                        "status": sync.get("status"),
                        "result": sync.get("result"),
                        "view": restart_view,
                        "components": sync.get("components"),
                        "request_fingerprint": sync.get("request_fingerprint"),
                        "execution_binding": sync.get("execution_binding"),
                    }) == sync_identity,
                    "restart_evidence_same": _evidence_identity(restart_evidence) == evidence_identity,
                    "artifact_available": bool(sync.get("artifact_ref")),
                    "view_answer_has_next_steps": "next_steps" in sync_view.get("answer", {}),
                },
            }
        finally:
            first.close()
            host.close()


if __name__ == "__main__":
    print(json.dumps(run_acceptance(), ensure_ascii=False))
