"""Bounded evidence for capability selection and clarification outcomes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SELECTION_EVIDENCE_SCHEMA_VERSION = "spatial-agent.selection-evidence.v1"
_MAX_CANDIDATES = 8
_MAX_LIST = 8
_PRIVATE_KEYS = {
    "api_key",
    "credential",
    "messages",
    "model_response",
    "password",
    "private_payload",
    "prompt",
    "raw_response",
    "secret",
    "source_path",
    "token",
}


def project_selection_evidence(
    context: Mapping[str, Any] | None,
    *,
    existing_selection: Mapping[str, Any] | None = None,
    existing_clarification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one safe selection summary from Context and planner evidence."""

    source = context if isinstance(context, Mapping) else {}
    existing = existing_selection if isinstance(existing_selection, Mapping) else {}
    candidates = _candidate_summaries(source.get("capability_index"))
    clarification = _clarification(
        existing_clarification
        if isinstance(existing_clarification, Mapping)
        else source.get("clarification")
    )
    discovery = source.get("discovery")
    discovery = discovery if isinstance(discovery, Mapping) else {}
    selected_keys = _strings(existing.get("selected_capability_keys"), _MAX_LIST)
    if not selected_keys:
        envelope = source.get("planner_envelope")
        envelope_selection = envelope.get("selection") if isinstance(envelope, Mapping) else {}
        if isinstance(envelope_selection, Mapping):
            selected_keys = _strings(
                envelope_selection.get("selected_capability_keys"), _MAX_LIST
            )
    selected_ids = _strings(existing.get("selected_capability_ids"), _MAX_LIST)
    return normalize_selection_evidence({
        "schema_version": SELECTION_EVIDENCE_SCHEMA_VERSION,
        "request_fingerprint": _text(source.get("request_fingerprint"), 128) or None,
        "requested_planner": _text(
            existing.get("requested_planner") or source.get("planner"), 32
        )
        or "unknown",
        "selected_source": _text(existing.get("selected_source"), 32) or "unknown",
        "state": _text(existing.get("state"), 32) or "unavailable",
        "reason_code": _text(existing.get("reason_code"), 96)
        or _text(discovery.get("reason_code"), 96)
        or "selection_unavailable",
        "candidate_count": len(candidates),
        "selected_capability_ids": selected_ids,
        "selected_capability_keys": selected_keys,
        "candidates": candidates,
        "clarification": clarification,
        "next_actions": _strings(
            clarification.get("next_actions")
            or discovery.get("next_actions"),
            4,
        ),
    })


def normalize_selection_evidence(value: Any) -> dict[str, Any]:
    """Sanitize an already projected selection summary for persistence/View."""

    if not isinstance(value, Mapping):
        return {}
    if str(value.get("schema_version") or "") != SELECTION_EVIDENCE_SCHEMA_VERSION:
        return {}
    candidates = _candidate_summaries(value.get("candidates"))
    clarification = _clarification(value.get("clarification"))
    try:
        candidate_count = max(
            len(candidates), min(16, max(0, int(value.get("candidate_count") or 0)))
        )
    except (TypeError, ValueError):
        candidate_count = len(candidates)
    return {
        "schema_version": SELECTION_EVIDENCE_SCHEMA_VERSION,
        "request_fingerprint": _text(value.get("request_fingerprint"), 128) or None,
        "requested_planner": _text(value.get("requested_planner"), 32) or "unknown",
        "selected_source": _text(value.get("selected_source"), 32) or "unknown",
        "state": _text(value.get("state"), 32) or "unavailable",
        "reason_code": _text(value.get("reason_code"), 96) or "selection_unavailable",
        "candidate_count": candidate_count,
        "selected_capability_ids": _strings(value.get("selected_capability_ids"), _MAX_LIST),
        "selected_capability_keys": _strings(value.get("selected_capability_keys"), _MAX_LIST),
        "candidates": candidates,
        "clarification": clarification,
        "next_actions": _strings(
            value.get("next_actions") or clarification.get("next_actions"), 4
        ),
    }


def _candidate_summaries(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in _sequence(value):
        if not isinstance(raw, Mapping):
            continue
        domain_id = _text(raw.get("domain_id"), 64)
        capability_id = _text(raw.get("capability_id"), 96)
        if not domain_id or not capability_id or (domain_id, capability_id) in seen:
            continue
        seen.add((domain_id, capability_id))
        profiles = []
        for profile in _sequence(
            raw.get("output_profiles") or raw.get("data_profiles")
        )[:_MAX_LIST]:
            if not isinstance(profile, Mapping):
                continue
            result_type = _text(profile.get("result_type"), 96)
            kinds = _strings(profile.get("kinds"), _MAX_LIST)
            if result_type and kinds:
                profiles.append(
                    {
                        "result_type": result_type,
                        "primary": _text(profile.get("primary"), 32) or kinds[0],
                        "kinds": kinds,
                    }
                )
        result.append(
            {
                "domain_id": domain_id,
                "capability_id": capability_id,
                "selection_key": _text(raw.get("selection_key"), 140)
                or f"{domain_id}::{capability_id}"[:140],
                "label": _text(raw.get("label"), 160),
                "available": bool(raw.get("available")),
                "availability_reason": _text(raw.get("availability_reason"), 160),
                "data_profiles": profiles,
                "result_types": _strings(raw.get("result_types"), 16),
                "workflow_ids": _strings(raw.get("workflow_ids"), _MAX_LIST),
                "execution_readiness": _text(raw.get("execution_readiness"), 32)
                or None,
                "execution_ready": (
                    bool(raw.get("execution_ready"))
                    if "execution_ready" in raw
                    else None
                ),
                "execution_reason_code": _text(raw.get("execution_reason_code"), 96)
                or None,
            }
        )
        if len(result) >= _MAX_CANDIDATES:
            break
    return result


def _clarification(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "state": _text(source.get("state"), 32) or "not_required",
        "reason_code": _text(source.get("reason_code"), 96) or "unknown",
        "message": _text(source.get("message"), 640),
        "missing_by_domain": _safe_value(
            source.get("missing_by_domain") or [], depth=0
        ),
        "next_actions": _strings(source.get("next_actions"), 4),
    }


def _safe_value(value: Any, *, depth: int) -> Any:
    if depth >= 2:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {
            str(key)[:96]: _safe_value(item, depth=depth + 1)
            for key, item in list(value.items())[:16]
            if str(key).strip().lower().replace("-", "_") not in _PRIVATE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth=depth + 1) for item in list(value)[:_MAX_LIST]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value)[:320] if isinstance(value, str) else value
    return str(value)[:160]


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return []
    return list(value)


def _strings(value: Any, limit: int) -> list[str]:
    values = [value] if isinstance(value, str) else _sequence(value)
    result: list[str] = []
    for item in values[:limit]:
        text = _text(item, 160)
        if text and text not in result:
            result.append(text)
    return result


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


__all__ = [
    "SELECTION_EVIDENCE_SCHEMA_VERSION",
    "normalize_selection_evidence",
    "project_selection_evidence",
]
