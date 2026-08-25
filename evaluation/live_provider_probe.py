"""Bounded, credential-free probe for an OpenAI-compatible provider."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from time import monotonic
from typing import Any

from evaluation.live_baseline import run_bounded_operation
from evaluation.model_evaluation import sanitize_provider_metrics


PROVIDER_PROBE_SCHEMA_VERSION = "spatial-agent.live-provider-probe.v1"
COMPOSITE_PLANNING_PROBE_SCHEMA_VERSION = "spatial-agent.composite-planning-probe.v1"
PROVIDER_PROBE_SCHEMA = {
    "type": "object",
    "properties": {"status": {"type": "string", "enum": ["ready"]}},
    "required": ["status"],
    "additionalProperties": False,
}
PROVIDER_PROBE_MESSAGES = (
    {
        "role": "system",
        "content": "Return only the requested JSON object. Do not include any other fields.",
    },
    {
        "role": "user",
        "content": "Respond with the JSON object {\"status\":\"ready\"}.",
    },
)
_SAFE_ID = re.compile(r"[^A-Za-z0-9._:/-]+")


def run_provider_probe(
    *,
    client_factory: Callable[[float], Any],
    timeout_seconds: float = 45.0,
) -> dict[str, Any]:
    """Run one structured provider request behind the M270 deadline seam."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    started = monotonic()
    deadline = started + float(timeout_seconds)
    try:
        receipt = run_bounded_operation(
            lambda: _probe_once(client_factory, float(timeout_seconds)),
            deadline=deadline,
            heartbeat_seconds=float(timeout_seconds),
            progress_callback=None,
            case_id="provider-probe",
            started=started,
        )
    except TimeoutError:
        return _timeout_receipt(started)
    except Exception:
        # The public receipt must remain stable even if a custom client factory
        # fails before it can expose provider metrics.
        return _failure_receipt(
            started,
            error_class="other",
            response_shape_valid=False,
        )
    return _bounded_receipt(receipt, started)


def _probe_once(client_factory: Callable[[float], Any], timeout_seconds: float) -> dict[str, Any]:
    client = None
    started = monotonic()
    try:
        client = client_factory(timeout_seconds)
        payload = client.complete_json(
            PROVIDER_PROBE_MESSAGES,
            PROVIDER_PROBE_SCHEMA,
            schema_name="provider_probe",
        )
    except Exception as exc:
        fallback_error = _exception_error_type(exc)
        return _failure_receipt(
            started,
            error_class=_safe_error_class(_client_metrics(client, fallback_error)),
            metrics=_client_metrics(client, fallback_error),
            response_shape_valid=False,
        )

    metrics = _client_metrics(client, None)
    if not _valid_probe_payload(payload):
        return _failure_receipt(
            started,
            error_class="invalid_response",
            metrics=metrics,
            response_shape_valid=False,
        )
    return _success_receipt(started, metrics)


def _valid_probe_payload(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"status"}
        and value.get("status") == "ready"
    )


def _client_metrics(client: Any, fallback_error: str | None) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    metrics = getattr(client, "metrics", None)
    if callable(metrics):
        try:
            value = metrics()
            if isinstance(value, Mapping):
                raw.update(value)
        except Exception:
            pass
    if fallback_error and not raw.get("error_type"):
        raw["error_type"] = fallback_error
    raw.setdefault("status", "error" if fallback_error else "success")
    raw.setdefault("attempts", 1)
    raw.setdefault("retries", 0)
    raw.setdefault("latency_ms", 0)
    return raw


def _success_receipt(started: float, raw_metrics: Mapping[str, Any]) -> dict[str, Any]:
    return _receipt(
        started,
        status="READY",
        error_class="none",
        response_shape_valid=True,
        raw_metrics=raw_metrics,
    )


def _failure_receipt(
    started: float,
    *,
    error_class: str,
    response_shape_valid: bool,
    metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _receipt(
        started,
        status="FAILED",
        error_class=error_class,
        response_shape_valid=response_shape_valid,
        raw_metrics=metrics or {},
    )


def _timeout_receipt(started: float) -> dict[str, Any]:
    return _failure_receipt(
        started,
        error_class="timeout",
        response_shape_valid=False,
        metrics={"error_type": "timeout", "status": "error", "attempts": 1, "retries": 0},
    )


def _receipt(
    started: float,
    *,
    status: str,
    error_class: str,
    response_shape_valid: bool,
    raw_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = dict(raw_metrics) if isinstance(raw_metrics, Mapping) else {}
    metrics["latency_ms"] = max(
        float(metrics.get("latency_ms") or 0),
        round((monotonic() - started) * 1000, 3),
    )
    safe_metrics = sanitize_provider_metrics(metrics)
    identity = {
        key: _safe_identity(metrics.get(key))
        for key in ("provider", "model", "wire_api")
        if metrics.get(key) is not None
    }
    return {
        "schema_version": PROVIDER_PROBE_SCHEMA_VERSION,
        "execution_mode": "live_model_probe",
        "status": status,
        "error_class": error_class,
        "response_shape_valid": bool(response_shape_valid),
        "provider": identity.get("provider", "unknown"),
        "model": identity.get("model", "unknown"),
        "wire_api": identity.get("wire_api", "unknown"),
        "metrics": safe_metrics,
        "passed": status == "READY" and error_class == "none" and response_shape_valid,
    }


def _bounded_receipt(receipt: Mapping[str, Any], started: float) -> dict[str, Any]:
    # `_probe_once` owns the shape; rebuild through the allowlisted projection
    # so a custom client cannot add arbitrary fields to the public report.
    metrics = receipt.get("metrics") if isinstance(receipt, Mapping) else {}
    safe_metrics = dict(metrics) if isinstance(metrics, Mapping) else sanitize_provider_metrics({})
    return {
        "schema_version": PROVIDER_PROBE_SCHEMA_VERSION,
        "execution_mode": "live_model_probe",
        "status": str(receipt.get("status") or "FAILED"),
        "error_class": str(receipt.get("error_class") or "other"),
        "response_shape_valid": bool(receipt.get("response_shape_valid")),
        "provider": _safe_identity(receipt.get("provider")),
        "model": _safe_identity(receipt.get("model")),
        "wire_api": _safe_identity(receipt.get("wire_api")),
        "metrics": safe_metrics,
        "passed": bool(receipt.get("passed")),
        "elapsed_ms": int(max(0.0, monotonic() - started) * 1000),
    }


def _exception_error_type(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "url" in name or "socket" in name:
        return "url_error"
    return "provider_error"


def _safe_error_class(metrics: Mapping[str, Any]) -> str:
    return str(sanitize_provider_metrics(metrics)["provider_error"]["class"])


def _safe_identity(value: Any) -> str:
    if value is None:
        return "unknown"
    normalized = _SAFE_ID.sub("_", str(value)).strip("_")
    return normalized[:96] or "unknown"


def run_composite_planning_probe(
    *,
    application: Any,
    request: str,
    planner_name: str = "openai",
    backend: str = "local",
    domain_ids: tuple[str, ...] = ("gis", "economic"),
    timeout_seconds: float = 45.0,
) -> dict[str, Any]:
    """Run one bounded planning-only probe without creating an execution run."""

    if application is None or not callable(getattr(application, "prepare", None)):
        raise ValueError("application must expose prepare()")
    if not str(request or "").strip():
        raise ValueError("request must not be empty")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    started = monotonic()
    try:
        receipt = run_bounded_operation(
            lambda: _composite_planning_once(
                application,
                request=str(request)[:2000],
                planner_name=str(planner_name)[:32],
                backend=str(backend)[:32],
                domain_ids=tuple(str(value)[:32] for value in domain_ids)[:8],
            ),
            deadline=started + float(timeout_seconds),
            heartbeat_seconds=float(timeout_seconds),
            progress_callback=None,
            case_id="composite-planning-probe",
            started=started,
        )
    except TimeoutError:
        return _composite_planning_receipt(
            started,
            status="FAILED",
            error_code="timeout",
            component_count=0,
            request_fingerprint=None,
            planner_evidence=None,
        )
    except Exception:
        return _composite_planning_receipt(
            started,
            status="FAILED",
            error_code="planning_probe_failed",
            component_count=0,
            request_fingerprint=None,
            planner_evidence=None,
        )
    return _bounded_composite_planning_receipt(receipt, started)


def _composite_planning_once(
    application: Any,
    *,
    request: str,
    planner_name: str,
    backend: str,
    domain_ids: tuple[str, ...],
) -> dict[str, Any]:
    try:
        result = application.prepare(
            request,
            planner_name=planner_name,
            backend=backend,
            domain_ids=list(domain_ids),
        )
    except Exception:
        return _composite_planning_receipt(
            monotonic(),
            status="FAILED",
            error_code="planning_probe_failed",
            component_count=0,
            request_fingerprint=None,
            planner_evidence=None,
        )
    if not isinstance(result, Mapping):
        return _composite_planning_receipt(
            monotonic(),
            status="FAILED",
            error_code="planning_response_invalid",
            component_count=0,
            request_fingerprint=None,
            planner_evidence=None,
        )
    status = str(result.get("status") or "REJECTED").upper()
    if status not in {"PLANNED", "NEEDS_CLARIFICATION", "REJECTED"}:
        status = "FAILED"
    components = result.get("components")
    component_count = len(components) if isinstance(components, list) else 0
    return _composite_planning_receipt(
        monotonic(),
        status=status,
        error_code=result.get("error_code"),
        component_count=component_count,
        request_fingerprint=result.get("request_fingerprint"),
        planner_evidence=result.get("planner_evidence"),
    )


def _composite_planning_receipt(
    started: float,
    *,
    status: str,
    error_code: Any,
    component_count: int,
    request_fingerprint: Any,
    planner_evidence: Any,
) -> dict[str, Any]:
    fingerprint = _safe_probe_string(request_fingerprint, 128)
    evidence = _safe_planner_evidence(planner_evidence)
    return {
        "schema_version": COMPOSITE_PLANNING_PROBE_SCHEMA_VERSION,
        "execution_mode": "live_composite_planning_probe",
        "status": status,
        "error_code": _safe_probe_string(error_code, 96) or None,
        "component_count": max(0, min(8, int(component_count))),
        "request_fingerprint": fingerprint or None,
        "planner_evidence": evidence,
        "passed": status == "PLANNED" and bool(fingerprint) and component_count > 0,
        "elapsed_ms": int(max(0.0, monotonic() - started) * 1000),
    }


def _bounded_composite_planning_receipt(
    receipt: Mapping[str, Any], started: float
) -> dict[str, Any]:
    return _composite_planning_receipt(
        started,
        status=str(receipt.get("status") or "FAILED"),
        error_code=receipt.get("error_code"),
        component_count=receipt.get("component_count") or 0,
        request_fingerprint=receipt.get("request_fingerprint"),
        planner_evidence=receipt.get("planner_evidence"),
    )


def _safe_planner_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    compatibility = value.get("compatibility")
    safe_compatibility = {"status": "identity", "actions": []}
    if isinstance(compatibility, Mapping):
        status = str(compatibility.get("status") or "identity")
        if status not in {"identity", "normalized"}:
            status = "identity"
        actions = []
        for action in compatibility.get("actions") or []:
            text = _safe_probe_string(action, 96)
            if text and text not in actions:
                actions.append(text)
            if len(actions) >= 16:
                break
        safe_compatibility = {"status": status, "actions": actions}
    return {
        "schema_version": _safe_probe_string(value.get("schema_version"), 96),
        "planner_source": _safe_probe_string(value.get("planner_source"), 32),
        "schema_status": _safe_probe_string(value.get("schema_status"), 32),
        "component_count": max(0, min(8, int(value.get("component_count") or 0))),
        "request_fingerprint": _safe_probe_string(value.get("request_fingerprint"), 128),
        "compatibility": safe_compatibility,
    }


def _safe_probe_string(value: Any, limit: int) -> str:
    if value is None:
        return ""
    normalized = _SAFE_ID.sub("_", str(value)).strip("_")
    return normalized[:limit]


__all__ = [
    "PROVIDER_PROBE_MESSAGES",
    "PROVIDER_PROBE_SCHEMA",
    "PROVIDER_PROBE_SCHEMA_VERSION",
    "COMPOSITE_PLANNING_PROBE_SCHEMA_VERSION",
    "run_composite_planning_probe",
    "run_provider_probe",
]
