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
MAX_REPORT_ITEMS = 24
MAX_REPORT_TEXT = 160
TERMINAL_STATES = {
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMED_OUT",
    "REJECTED",
    "NEEDS_CLARIFICATION",
}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
SAFE_DOMAIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SAME_RUN_FIELDS = (
    "result_type",
    "model_evidence",
    "context_fingerprint",
    "plan_identity",
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
    requested_domain = _requested_domain(args)
    if args.verify_run_id:
        return _verify_existing_run(base_url, args.verify_run_id, args)
    common = {
        "request": args.request,
        "session_id": "live-http-" + uuid.uuid4().hex,
        "planner": args.planner,
        "backend": args.backend,
        "export_artifact": True,
        "timeout_seconds": args.request_timeout,
        "idempotency_key": "live-http-" + uuid.uuid4().hex,
    }
    if requested_domain == "auto":
        submit_path = "/runs/auto"
        async_payload = {**common, "async": True}
    else:
        submit_path = f"/domains/{quote(requested_domain)}/runs/async"
        async_payload = common
    queued = _json_request(
        base_url, "POST", submit_path, async_payload, args.http_timeout
    )
    if str(queued.get("status") or "").upper() == "NEEDS_CLARIFICATION":
        raise AcceptanceFailure("automatic domain selection needs clarification")
    domain_id = _selected_domain(queued, requested_domain)
    run_id = _run_id(queued)
    observation = _poll_async(base_url, domain_id, run_id, args)
    async_full = _json_request(
        base_url,
        "GET",
        _domain_path(domain_id, "/runs/" + quote(run_id)) + "?" + urlencode({
            "planner": args.planner,
            "backend": args.backend,
        }),
        None,
        args.http_timeout,
    )
    _completed(async_full, "async run")
    async_bundle = _artifact_bundle(
        base_url, async_full, args.http_timeout, domain_id=domain_id
    )

    async_contract = _full_contract(async_full)
    _match(
        "async/artifact",
        async_contract,
        _full_contract(async_bundle["artifact"]),
        SAME_RUN_FIELDS,
    )
    _match(
        "async polling/artifact",
        _poll_contract(observation),
        async_contract,
        SAME_RUN_FIELDS,
    )
    _match(
        "async evidence endpoints",
        _evidence_contract(async_bundle["run_evidence"]),
        _evidence_contract(async_bundle["artifact_evidence"]),
        ("registry", "projection", "recovery"),
    )

    report = {
        "status": "ok",
        "mode": "async_first_live_execution",
        "domain_selection": {
            "requested": requested_domain,
            "selected": domain_id,
        },
        "planner": args.planner,
        "backend": args.backend,
        "result_type": _safe_text(async_contract["result_type"]),
        "model_evidence": async_contract["model_evidence"],
        "context_fingerprint": _safe_text(async_contract["context_fingerprint"]),
        "plan_identity": _safe_plan_identity(async_contract["plan_identity"]),
        "workspace_panels": _bounded_ids(async_contract["workspace_panels"]),
        "view_panel_ids": _bounded_mapping(async_contract["view_kinds"]),
        "async": {
            "status": _safe_text(async_full.get("status")),
            "poll_status": _safe_text(observation.get("status")),
            "artifact_available": True,
            "agent_run_submissions": 1,
        },
        "comparisons": {
            "async_artifact": "ok",
            "async_polling_artifact": "ok",
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
    domain_option = _requested_domain(args)
    requested_domain = None if domain_option == "auto" else domain_option
    full = _json_request(
        base_url,
        "GET",
        _domain_path(requested_domain, "/runs/" + quote(run_id)) + "?" + urlencode({
            "planner": args.planner,
            "backend": args.backend,
        }),
        None,
        args.http_timeout,
    )
    _completed(full, "recovered run")
    domain_id = _selected_domain(full, domain_option, allow_legacy_auto=True)
    observation = _json_request(
        base_url,
        "GET",
        _domain_path(domain_id, f"/runs/{quote(run_id)}/async"),
        None,
        args.http_timeout,
    )
    bundle = _artifact_bundle(
        base_url, full, args.http_timeout, domain_id=domain_id
    )
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
        "domain_selection": {
            "requested": domain_option,
            "selected": domain_id,
        },
        "planner": args.planner,
        "backend": args.backend,
        "result_type": _safe_text(contract["result_type"]),
        "model_evidence": contract["model_evidence"],
        "context_fingerprint": _safe_text(contract["context_fingerprint"]),
        "plan_identity": _safe_plan_identity(contract["plan_identity"]),
        "workspace_panels": _bounded_ids(contract["workspace_panels"]),
        "view_panel_ids": _bounded_mapping(contract["view_kinds"]),
        "recovery": {
            "status": _safe_text(observation.get("status")),
            "recovery_count": _safe_number(observation.get("recovery_count")),
            "last_event": _safe_text(observation.get("last_event")),
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


def _artifact_bundle(
    base_url: str,
    payload: Mapping[str, Any],
    timeout: float,
    *,
    domain_id: Optional[str] = None,
):
    name = _artifact_name(payload)
    if not name:
        raise AcceptanceFailure("artifact reference is missing")
    run_id = _run_id(payload)
    prefix = _domain_path(domain_id, "/artifacts/runs/" + quote(name))
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
            base_url,
            "GET",
            _domain_path(domain_id, f"/runs/{quote(run_id)}/evidence"),
            None,
            timeout,
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
    result = {
        key: _safe_report_value(value[key])
        for key in allowed
        if key in value
    }
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
    domain_id: str,
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
            _domain_path(domain_id, f"/runs/{quote(run_id)}/async"),
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
    if not isinstance(value, str) or not SAFE_NAME.fullmatch(value.strip()):
        raise AcceptanceFailure("run_id is missing")
    return value.strip()


def _requested_domain(args: argparse.Namespace) -> str:
    value = str(getattr(args, "domain", "auto") or "auto").strip()
    if value == "auto" or SAFE_DOMAIN.fullmatch(value):
        return value
    raise AcceptanceFailure("domain must be auto or a safe domain identifier")


def _selected_domain(
    payload: Mapping[str, Any],
    requested: str,
    *,
    allow_legacy_auto: bool = False,
) -> str:
    value = payload.get("domain_id")
    if not isinstance(value, str) or not SAFE_DOMAIN.fullmatch(value.strip()):
        if requested != "auto":
            value = requested
        elif allow_legacy_auto:
            value = "gis"
        else:
            raise AcceptanceFailure("selected domain is missing or invalid")
    value = value.strip()
    if requested != "auto" and value != requested:
        raise AcceptanceFailure("selected domain does not match explicit domain")
    return value


def _domain_path(domain_id: Optional[str], suffix: str) -> str:
    if not domain_id:
        return suffix
    if not SAFE_DOMAIN.fullmatch(domain_id):
        raise AcceptanceFailure("domain identifier is invalid")
    return f"/domains/{quote(domain_id)}{suffix}"


def _safe_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value).replace("\r", " ").replace("\n", " ")[:MAX_REPORT_TEXT]


def _safe_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _safe_report_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    return _safe_text(value)


def _safe_plan_identity(value: Any) -> Dict[str, Optional[str]]:
    value = value if isinstance(value, Mapping) else {}
    return {
        "version": _safe_text(value.get("version")),
        "fingerprint": _safe_text(value.get("fingerprint")),
    }


def _bounded_ids(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in value[:MAX_REPORT_ITEMS]:
        identity = item.get("id") if isinstance(item, Mapping) else item
        safe = _safe_text(identity)
        if safe:
            result.append(safe)
    return result


def _bounded_mapping(value: Any) -> Dict[str, Optional[str]]:
    if not isinstance(value, Mapping):
        return {}
    result: Dict[str, Optional[str]] = {}
    for key, item in list(value.items())[:MAX_REPORT_ITEMS]:
        safe_key = _safe_text(key)
        if safe_key:
            result[safe_key] = _safe_text(item)
    return result


def _completed(payload: Mapping[str, Any], label: str) -> None:
    status = _safe_text(payload.get("status") or "missing")
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
    parser.add_argument(
        "--domain",
        default="auto",
        metavar="DOMAIN|auto",
        help="auto routes once before submitting the selected domain asynchronously",
    )
    parser.add_argument("--request", default="查询DEM栅格元数据")
    parser.add_argument("--request-timeout", type=float, default=45.0)
    parser.add_argument("--http-timeout", type=float, default=30.0)
    parser.add_argument("--poll-limit", type=int, default=360)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--verify-run-id")
    parser.add_argument("--include-run-id", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
