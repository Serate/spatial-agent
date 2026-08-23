"""Opt-in live HTTP/async/artifact acceptance with bounded output."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.contract_harness import normalize_result


LIVE_ENV = "SPATIAL_AGENT_LIVE_HTTP"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
TERMINAL_STATES = {
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMED_OUT",
    "REJECTED",
    "NEEDS_CLARIFICATION",
}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
SAME_RUN_FIELDS = (
    "result_type",
    "model_evidence",
    "context_fingerprint",
    "plan_identity",
    "workspace_panels",
    "view_panels",
    "view_kinds",
)
CROSS_RUN_FIELDS = (
    "result_type",
    "model_identity",
    "context_fingerprint",
    "workspace_panels",
    "view_panels",
    "view_kinds",
)


class AcceptanceFailure(RuntimeError):
    pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if not args.allow_live and os.environ.get(LIVE_ENV, "").lower() not in {
        "1",
        "true",
        "yes",
    }:
        print(json.dumps({
            "status": "skipped",
            "reason_code": "live_http_opt_in_required",
            "enable_with": f"{LIVE_ENV}=1",
        }))
        return 2
    try:
        report = run_acceptance(args)
    except AcceptanceFailure as exc:
        print(json.dumps({
            "status": "failed",
            "reason_code": "live_http_acceptance_failed",
            "error_type": type(exc).__name__,
            "message": str(exc)[:240],
        }))
        return 1
    except Exception as exc:  # pragma: no cover - final redaction boundary
        print(json.dumps({
            "status": "failed",
            "reason_code": "live_http_acceptance_unexpected_error",
            "error_type": type(exc).__name__,
        }))
        return 1
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


def run_acceptance(args: argparse.Namespace) -> Dict[str, Any]:
    base_url = _base_url(args.base_url)
    if args.verify_run_id:
        return _verify_existing_run(base_url, args.verify_run_id, args)
    common = {
        "request": args.request,
        "session_id": "live-http-" + uuid.uuid4().hex,
        "planner": args.planner,
        "backend": args.backend,
        "export_artifact": True,
        "timeout_seconds": args.request_timeout,
    }

    sync = _json_request(base_url, "POST", "/runs", common, args.http_timeout)
    _completed(sync, "sync run")
    sync_bundle = _artifact_bundle(base_url, sync, args.http_timeout)

    async_payload = {
        **common,
        "idempotency_key": "live-http-" + uuid.uuid4().hex,
    }
    queued = _json_request(
        base_url, "POST", "/runs/async", async_payload, args.http_timeout
    )
    run_id = _run_id(queued)
    duplicate = _json_request(
        base_url, "POST", "/runs/async", async_payload, args.http_timeout
    )
    if _run_id(duplicate) != run_id or duplicate.get("idempotent") is not True:
        raise AcceptanceFailure("async duplicate submission was not idempotent")
    observation = _poll_async(base_url, run_id, args)
    async_full = _json_request(
        base_url,
        "GET",
        "/runs/" + quote(run_id) + "?" + urlencode({
            "planner": args.planner,
            "backend": args.backend,
        }),
        None,
        args.http_timeout,
    )
    _completed(async_full, "async run")
    async_bundle = _artifact_bundle(base_url, async_full, args.http_timeout)

    sync_contract = _full_contract(sync)
    async_contract = _full_contract(async_full)
    _match(
        "sync/artifact",
        sync_contract,
        _full_contract(sync_bundle["artifact"]),
        SAME_RUN_FIELDS,
    )
    _match(
        "async/artifact",
        async_contract,
        _full_contract(async_bundle["artifact"]),
        SAME_RUN_FIELDS,
    )
    _match("sync/async core", sync_contract, async_contract, CROSS_RUN_FIELDS)
    _match(
        "async polling/artifact",
        _poll_contract(observation),
        async_contract,
        SAME_RUN_FIELDS,
    )
    _match(
        "sync evidence endpoints",
        _evidence_contract(sync_bundle["run_evidence"]),
        _evidence_contract(sync_bundle["artifact_evidence"]),
        ("registry", "projection", "recovery"),
    )
    _match(
        "async evidence endpoints",
        _evidence_contract(async_bundle["run_evidence"]),
        _evidence_contract(async_bundle["artifact_evidence"]),
        ("registry", "projection", "recovery"),
    )

    report = {
        "status": "ok",
        "mode": "live_execution",
        "planner": args.planner,
        "backend": args.backend,
        "result_type": async_contract["result_type"],
        "model_evidence": async_contract["model_evidence"],
        "context_fingerprint": async_contract["context_fingerprint"],
        "plan_identity": {
            "sync": sync_contract["plan_identity"],
            "async": async_contract["plan_identity"],
            "same_across_independent_runs": (
                sync_contract["plan_identity"] == async_contract["plan_identity"]
            ),
        },
        "workspace_panels": async_contract["workspace_panels"],
        "view_panel_ids": async_contract["view_kinds"],
        "sync": {"status": sync.get("status"), "artifact_available": True},
        "async": {
            "status": async_full.get("status"),
            "poll_status": observation.get("status"),
            "artifact_available": True,
            "idempotent_submission": True,
        },
        "comparisons": {
            "sync_artifact": "ok",
            "async_artifact": "ok",
            "sync_async_core": "ok",
            "async_polling_artifact": "ok",
            "sync_evidence_endpoints": "ok",
            "async_evidence_endpoints": "ok",
        },
    }
    if args.include_run_id:
        report["async"]["run_id"] = run_id
    return report


def _verify_existing_run(
    base_url: str,
    run_id: str,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    full = _json_request(
        base_url,
        "GET",
        "/runs/" + quote(run_id) + "?" + urlencode({
            "planner": args.planner,
            "backend": args.backend,
        }),
        None,
        args.http_timeout,
    )
    _completed(full, "recovered run")
    observation = _json_request(
        base_url,
        "GET",
        f"/runs/{quote(run_id)}/async",
        None,
        args.http_timeout,
    )
    bundle = _artifact_bundle(base_url, full, args.http_timeout)
    contract = _full_contract(full)
    _match(
        "recovered run/artifact",
        contract,
        _full_contract(bundle["artifact"]),
        SAME_RUN_FIELDS,
    )
    _match(
        "recovered polling/artifact",
        _poll_contract(observation),
        contract,
        SAME_RUN_FIELDS,
    )
    _match(
        "recovered evidence endpoints",
        _evidence_contract(bundle["run_evidence"]),
        _evidence_contract(bundle["artifact_evidence"]),
        ("registry", "projection", "recovery"),
    )
    report = {
        "status": "ok",
        "mode": "existing_run_verification",
        "planner": args.planner,
        "backend": args.backend,
        "result_type": contract["result_type"],
        "model_evidence": contract["model_evidence"],
        "context_fingerprint": contract["context_fingerprint"],
        "plan_identity": contract["plan_identity"],
        "workspace_panels": contract["workspace_panels"],
        "view_panel_ids": contract["view_kinds"],
        "recovery": {
            "status": observation.get("status"),
            "recovery_count": observation.get("recovery_count"),
            "last_event": observation.get("last_event"),
            "artifact_available": True,
        },
        "comparisons": {
            "run_artifact": "ok",
            "polling_artifact": "ok",
            "evidence_endpoints": "ok",
        },
    }
    if args.include_run_id:
        report["run_id"] = run_id
    return report


def _artifact_bundle(base_url: str, payload: Mapping[str, Any], timeout: float):
    name = _artifact_name(payload)
    if not name:
        raise AcceptanceFailure("artifact reference is missing")
    run_id = _run_id(payload)
    prefix = "/artifacts/runs/" + quote(name)
    artifact = _json_request(base_url, "GET", prefix, None, timeout)
    manifest = _json_request(base_url, "GET", prefix + "/manifest", None, timeout)
    manifest_ref = manifest.get("artifact")
    if not isinstance(manifest_ref, Mapping) or not manifest_ref.get("available"):
        raise AcceptanceFailure("artifact manifest is unavailable")
    if manifest_ref.get("ref") != name:
        raise AcceptanceFailure("artifact manifest reference mismatch")
    return {
        "artifact": artifact,
        "run_evidence": _json_request(
            base_url, "GET", f"/runs/{quote(run_id)}/evidence", None, timeout
        ),
        "artifact_evidence": _json_request(
            base_url, "GET", prefix + "/evidence", None, timeout
        ),
    }


def _full_contract(payload: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        value = normalize_result(payload).as_dict()
    except ValueError as exc:
        raise AcceptanceFailure("full result contract is unavailable") from exc
    model = _safe_model(value.get("model_evidence"))
    runtime = value.get("runtime_context")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    return {
        "result_type": value.get("result_type"),
        "model_evidence": model,
        "model_identity": _model_identity(model),
        "context_fingerprint": (
            model.get("context_fingerprint")
            or runtime.get("fingerprint")
            or value.get("provenance_context_fingerprint")
        ),
        "plan_identity": {
            "version": value.get("plan_identity_version"),
            "fingerprint": value.get("plan_identity_fingerprint"),
        },
        "workspace_panels": value.get("workspace_panels") or [],
        "view_panels": value.get("view_panels") or [],
        "view_kinds": value.get("view_kinds") or {},
    }


def _poll_contract(payload: Mapping[str, Any]) -> Dict[str, Any]:
    value = payload.get("result_evidence")
    if not isinstance(value, Mapping):
        raise AcceptanceFailure("async result evidence is missing")
    planning = value.get("planning")
    planning = planning if isinstance(planning, Mapping) else {}
    identity = planning.get("plan_identity")
    identity = identity if isinstance(identity, Mapping) else {}
    workspace = value.get("workspace")
    workspace = workspace if isinstance(workspace, Mapping) else {}
    views = value.get("views")
    views = views if isinstance(views, Mapping) else {}
    panels = views.get("panels")
    panels = panels if isinstance(panels, Mapping) else {}
    model = _safe_model(value.get("model_evidence"))
    return {
        "result_type": value.get("result_type"),
        "model_evidence": model,
        "model_identity": _model_identity(model),
        "context_fingerprint": model.get("context_fingerprint"),
        "plan_identity": {
            "version": identity.get("version"),
            "fingerprint": identity.get("fingerprint"),
        },
        "workspace_panels": workspace.get("panels") or [],
        "view_panels": sorted(str(key) for key in panels),
        "view_kinds": {
            str(key): item.get("kind")
            for key, item in sorted(panels.items(), key=lambda pair: str(pair[0]))
            if isinstance(item, Mapping)
        },
    }


def _evidence_contract(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "registry": payload.get("evidence_registry"),
        "projection": payload.get("evidence_projection"),
        "recovery": payload.get("evidence_recovery"),
    }


def _safe_model(value: Any) -> Dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    allowed = (
        "schema_version",
        "available",
        "execution_mode",
        "context_fingerprint",
        "provider",
        "model",
        "wire_api",
        "status",
        "error_type",
        "fixture_id",
        "attempts",
        "retries",
        "latency_ms",
    )
    result = {key: value[key] for key in allowed if key in value}
    usage = value.get("usage")
    if isinstance(usage, Mapping):
        result["usage"] = {
            key: usage[key]
            for key in (
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "prompt_tokens",
                "completion_tokens",
            )
            if isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool)
        }
    return result


def _model_identity(value: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: value[key]
        for key in (
            "schema_version",
            "available",
            "execution_mode",
            "provider",
            "model",
            "wire_api",
        )
        if key in value
    }


def _json_request(
    base_url: str,
    method: str,
    path: str,
    payload: Optional[Mapping[str, Any]],
    timeout: float,
) -> Dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = Request(
        urljoin(base_url, path.lstrip("/")),
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=max(1.0, timeout)) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise AcceptanceFailure(f"HTTP {exc.code} for {method} {path}") from exc
    except (URLError, TimeoutError) as exc:
        raise AcceptanceFailure(
            f"transport failure for {method} {path}: {type(exc).__name__}"
        ) from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise AcceptanceFailure(f"response too large for {method} {path}")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceFailure(f"non-JSON response for {method} {path}") from exc
    if not isinstance(value, Mapping):
        raise AcceptanceFailure(f"JSON object expected for {method} {path}")
    return dict(value)


def _poll_async(
    base_url: str,
    run_id: str,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    if args.poll_limit < 1 or args.poll_limit > 600:
        raise AcceptanceFailure("poll limit must be between 1 and 600")
    latest: Dict[str, Any] = {}
    for index in range(args.poll_limit):
        latest = _json_request(
            base_url,
            "GET",
            f"/runs/{quote(run_id)}/async",
            None,
            args.http_timeout,
        )
        if str(latest.get("status") or "").upper() in TERMINAL_STATES:
            return latest
        if index + 1 < args.poll_limit:
            time.sleep(max(0.01, min(args.poll_interval, 5.0)))
    raise AcceptanceFailure("async run did not reach a terminal state")


def _artifact_name(payload: Mapping[str, Any]) -> Optional[str]:
    raw = payload.get("artifact_ref")
    if isinstance(raw, Mapping):
        raw = raw.get("ref")
    if not isinstance(raw, str):
        return None
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    return name if SAFE_NAME.fullmatch(name) and name.endswith(".json") else None


def _run_id(payload: Mapping[str, Any]) -> str:
    value = payload.get("run_id")
    if not isinstance(value, str) or not value.strip():
        raise AcceptanceFailure("run_id is missing")
    return value.strip()


def _completed(payload: Mapping[str, Any], label: str) -> None:
    status = str(payload.get("status") or "missing")
    if status != "COMPLETED":
        raise AcceptanceFailure(f"{label} status={status}")


def _match(
    label: str,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    fields: Sequence[str],
) -> None:
    mismatches = [field for field in fields if left.get(field) != right.get(field)]
    if mismatches:
        raise AcceptanceFailure(f"{label} contract drift: {','.join(mismatches)}")


def _base_url(value: str) -> str:
    value = str(value or "").strip()
    if not value.startswith(("http://", "https://")):
        raise AcceptanceFailure("base URL must use http or https")
    return value.rstrip("/") + "/"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--planner", choices=("rule", "openai"), default="openai")
    parser.add_argument("--backend", choices=("memory", "local"), default="memory")
    parser.add_argument("--request", default="查询DEM栅格元数据")
    parser.add_argument("--request-timeout", type=float, default=45.0)
    parser.add_argument("--http-timeout", type=float, default=30.0)
    parser.add_argument("--poll-limit", type=int, default=80)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--verify-run-id")
    parser.add_argument("--include-run-id", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
