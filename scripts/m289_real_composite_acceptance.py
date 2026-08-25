"""Explicit Docker acceptance for one prepared Composite plan across run entries."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

import production_api


def run_acceptance(
    request: str,
    *,
    planner_name: str = "openai",
    backend: str = "local",
    domain_ids: tuple[str, ...] = ("gis", "economic"),
    timeout_seconds: float = 90.0,
) -> dict[str, Any]:
    """Plan once, then compare sync/async execution without exposing raw output."""

    prepared = production_api.composite_planning_application.prepare(
        request[:2000],
        planner_name=planner_name[:32],
        backend=backend[:32],
        domain_ids=list(domain_ids)[:8],
    )
    return run_prepared_acceptance(
        prepared,
        run_application=production_api.composite_application,
        timeout_seconds=timeout_seconds,
    )


def run_prepared_acceptance(
    prepared: Mapping[str, Any],
    *,
    run_application: Any,
    timeout_seconds: float = 90.0,
) -> dict[str, Any]:
    """Execute one prepared plan through sync and async seams without replanning."""

    planning = _planning_receipt(prepared)
    if planning["status"] != "PLANNED":
        return {"planning": planning, "passed": False}
    canonical = prepared.get("request")
    if not isinstance(canonical, Mapping):
        return {
            "planning": planning,
            "passed": False,
            "error_code": "canonical_request_missing",
        }

    evidence = prepared.get("planner_evidence")
    sync = run_application.run_with_planning(
        canonical,
        session_id="m289-sync",
        export_artifact=True,
        planner_evidence=evidence if isinstance(evidence, Mapping) else None,
    )
    async_submission = run_application.submit_async_with_planning(
        canonical,
        session_id="m289-async",
        idempotency_key="m289-async-1",
        export_artifact=True,
        planner_evidence=evidence if isinstance(evidence, Mapping) else None,
    )
    async_detail = _wait_for_terminal(
        run_application, str(async_submission.get("run_id") or ""), timeout_seconds
    )
    comparison = _compare_results(sync, async_detail)
    return {
        "planning": planning,
        "sync": _execution_receipt(sync),
        "async": _execution_receipt(async_detail),
        "comparison": comparison,
        "passed": bool(comparison["same_result_type"] and comparison["same_component_states"]),
    }


def _wait_for_terminal(run_application: Any, run_id: str, timeout_seconds: float) -> Mapping[str, Any]:
    if not run_id:
        return {"status": "FAILED", "error_code": "async_run_id_missing"}
    deadline = time.time() + max(1.0, min(180.0, float(timeout_seconds)))
    while time.time() < deadline:
        detail = run_application.get_run(run_id)
        if str(detail.get("status") or "").upper() in {
            "COMPLETED",
            "PARTIAL",
            "FAILED",
            "BLOCKED",
        }:
            return detail
        time.sleep(0.1)
    return {"status": "TIMED_OUT", "error_code": "async_acceptance_timeout"}


def _planning_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": _text(value.get("status"), 32) or "FAILED",
        "error_code": _text(value.get("error_code"), 96) or None,
        "component_count": _bounded_count(value.get("components")),
        "request_fingerprint": _text(value.get("request_fingerprint"), 128) or None,
        "execution_run_created": bool(_text(value.get("run_id"), 160)),
        "structured_output": _structured_output(value.get("planner_evidence")),
    }


def _execution_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    result = value.get("result") if isinstance(value.get("result"), Mapping) else {}
    components = value.get("components") or result.get("components")
    return {
        "status": _text(value.get("status"), 32) or "FAILED",
        "error_code": _text(value.get("error_code"), 96) or None,
        "run_created": bool(_text(value.get("run_id"), 160)),
        "result_type": _text(result.get("type"), 96) or None,
        "component_states": _component_states(components),
        "artifact_available": bool(_text(value.get("artifact_ref"), 240)),
    }


def _compare_results(sync: Mapping[str, Any], asynchronous: Mapping[str, Any]) -> dict[str, Any]:
    sync_result = sync.get("result") if isinstance(sync.get("result"), Mapping) else {}
    async_result = asynchronous.get("result") if isinstance(asynchronous.get("result"), Mapping) else {}
    return {
        "same_result_type": sync_result.get("type") == async_result.get("type"),
        "same_component_states": _component_states(sync.get("components"))
        == _component_states(asynchronous.get("components")),
    }


def _component_states(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "component_id": _text(item.get("component_id"), 96),
            "state": _text(item.get("state"), 32),
            "status": _text(item.get("status"), 32),
        }
        for item in value[:8]
        if isinstance(item, Mapping)
    ]


def _structured_output(value: Any) -> dict[str, Any] | None:
    evidence = value if isinstance(value, Mapping) else {}
    profile = evidence.get("structured_output")
    if not isinstance(profile, Mapping):
        return None
    return {
        key: profile[key]
        for key in (
            "schema_version",
            "wire_api",
            "structured_mode",
            "schema_enforced",
            "source",
            "reason_code",
            "status",
        )
        if key in profile
    }


def _bounded_count(value: Any) -> int:
    return max(0, min(8, len(value))) if isinstance(value, list) else 0


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--planner", default="openai")
    parser.add_argument("--backend", default="local")
    parser.add_argument("--domains", default="gis,economic")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args()
    report = run_acceptance(
        args.request,
        planner_name=args.planner,
        backend=args.backend,
        domain_ids=tuple(value.strip() for value in args.domains.split(",") if value.strip()),
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
