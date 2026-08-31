"""Safe, bounded projection and sanitization of answer-generation evidence.

This is the deep seam between answer generation orchestration and any public
surface (Result, async, Artifact, Console).  Callers ask for a small number of
projection functions; everything inside is deliberately redacted so model
metadata, prompts, raw responses and request text never cross into public
evidence.  Do not add new fields here without keeping them allowlisted.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from .errors import PlanningError
from .answer_quality import project_answer_quality


# The canonical schema owner moved here with the evidence cluster.  Re-exported
# by the legacy ``agent.answer_generation`` facade to keep imports stable.
ANSWER_GENERATION_SCHEMA_VERSION = "spatial-agent.answer-generation.v1"

_MAX_MAPPING_ITEMS = 32
_MAX_LIST_ITEMS = 12
_MAX_STRING_CHARS = 240
_OMITTED_KEYS = {
    "api_key",
    "authorization",
    "credentials",
    "password",
    "secret",
    "token",
    "raw_response",
    "prompt",
    "messages",
    "geometry",
    "coordinates",
    "features",
    "geojson",
    "result_ref",
    "artifact_ref",
    "path",
    "file_path",
    "dataset_path",
}


def fallback_answer_generation_evidence(
    reason_code: str,
    *,
    metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return safe evidence when template fallback was used."""

    evidence = project_answer_generation_evidence(
        metrics or {},
        status="fallback",
        available=False,
    )
    evidence["reason_code"] = _safe_reason_code(reason_code)
    return evidence


def project_answer_generation_evidence(
    value: Mapping[str, Any] | None,
    *,
    status: str | None = None,
    available: bool | None = None,
) -> dict[str, Any]:
    """Allowlist answer-generation metrics for result/async/artifact surfaces."""

    source = value if isinstance(value, Mapping) else {}
    normalized_status = _safe_text(
        status if status is not None else source.get("status", "unavailable"),
        32,
    )
    execution_mode = source.get("execution_mode")
    existing_mode = source.get("mode")
    result: dict[str, Any] = {
        "schema_version": ANSWER_GENERATION_SCHEMA_VERSION,
        "available": bool(
            available if available is not None else source.get("available", False)
        ),
        "status": normalized_status,
        "mode": (
            "template_fallback"
            if normalized_status == "fallback"
            else existing_mode
            if existing_mode in {"live_model", "template_fallback"}
            else "live_model"
            if execution_mode == "live_model"
            else "template_fallback"
            if normalized_status == "fallback"
            else "unknown"
        ),
    }
    for key in ("provider", "model", "wire_api", "error_type", "reason_code"):
        if source.get(key):
            safe_value = _safe_evidence_text(source[key])
            if safe_value:
                result[key] = safe_value
    if normalized_status == "fallback" and "reason_code" not in result:
        result["reason_code"] = "generation_unavailable"
    if isinstance(source.get("streaming"), bool):
        result["streaming"] = source["streaming"]
    quality = project_answer_quality(source.get("quality"))
    if quality is not None:
        result["quality"] = quality
    for key in ("attempts", "retries", "compact_recovery_attempts"):
        try:
            number = int(source.get(key))
        except (TypeError, ValueError):
            continue
        if 0 <= number <= 32:
            result[key] = number
    try:
        latency = float(source.get("latency_ms"))
        if math.isfinite(latency) and latency >= 0:
            result["latency_ms"] = round(min(latency, 86_400_000), 3)
    except (TypeError, ValueError):
        pass
    usage = source.get("usage")
    if isinstance(usage, Mapping):
        safe_usage = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            try:
                number = int(usage.get(key))
            except (TypeError, ValueError):
                continue
            if 0 <= number <= 10_000_000:
                safe_usage[key] = number
        if safe_usage:
            result["usage"] = safe_usage
    return result


def _project_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    normalized_key = str(key or "").lower()
    if normalized_key in _OMITTED_KEYS or any(token in normalized_key for token in ("password", "secret", "token")):
        return None
    if value is None or isinstance(value, (bool, int, str)):
        return _safe_text(value, _MAX_STRING_CHARS) if isinstance(value, str) else value
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    if depth >= 4:
        return "…"
    if isinstance(value, Mapping):
        projected = {}
        for name, child in list(value.items())[:_MAX_MAPPING_ITEMS]:
            child_key = str(name)[:96]
            child_value = _project_value(child, key=child_key, depth=depth + 1)
            if child_value is not None:
                projected[child_key] = child_value
        return projected
    if isinstance(value, (list, tuple)):
        return [
            child
            for child in (
                _project_value(item, key=normalized_key, depth=depth + 1)
                for item in list(value)[:_MAX_LIST_ITEMS]
            )
            if child is not None
        ]
    return _safe_text(value, _MAX_STRING_CHARS)


def _safe_text(value: Any, limit: int) -> str:
    text = str(value or "")
    return text[:limit]


def _safe_evidence_text(value: Any) -> str:
    text = _safe_text(value, 96)
    lowered = text.lower()
    if any(marker in lowered for marker in ("prompt", "memory://", "artifact://", "result_ref", "tool_args")):
        return ""
    return text


def _safe_reason_code(value: Any) -> str:
    text = _safe_text(value, 96)
    return text if re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", text) else "generation_unavailable"


def _normalize_stream_text(value: Any, *, max_length: int) -> str:
    """Normalize a visible delta without persisting provider metadata."""

    if not isinstance(value, str) or max_length <= 0:
        return ""
    return value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")[:max_length]


def _contains_internal_reference(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("memory://", "artifact://", "result_ref", "prompt"))


def _is_stream_fallback_eligible(error: PlanningError) -> bool:
    """Allow a visible-answer fallback for bounded stream shape failures.

    A relay may finish with reasoning-only chunks or reject SSE while its
    structured endpoint remains usable. The fallback still validates the
    answer schema; it never exposes those chunks or bypasses the budget.
    """

    return getattr(error, "code", None) in {
        "stream_unsupported",
        "invalid_model_response",
        "provider_timeout",
    }


def _stream_fallback_reason(error: Exception) -> str:
    code = str(getattr(error, "code", "") or "").strip()
    return code if code in {
        "stream_unsupported",
        "invalid_model_response",
        "provider_timeout",
    } else "stream_unsupported"


def _normalize_composite_answer(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PlanningError("composite answer must be an object")
    allowed = {"headline", "summary", "key_findings", "limitations", "next_steps"}
    required = {"headline", "summary", "key_findings", "limitations"}
    if not required.issubset(set(value)) or not set(value).issubset(allowed):
        raise PlanningError("composite answer fields are invalid")
    answer: dict[str, Any] = {
        "headline": _safe_text(value.get("headline"), 160).strip(),
        "summary": _safe_text(value.get("summary"), 800).strip(),
    }
    if not answer["headline"] or not answer["summary"]:
        raise PlanningError("composite answer headline and summary are required")
    for key in ("key_findings", "limitations", "next_steps"):
        values = value.get(key)
        if values is None and key == "next_steps":
            values = []
        if not isinstance(values, list):
            raise PlanningError("composite answer lists are invalid")
        answer[key] = [_safe_text(item, 320).strip() for item in values[:8] if _safe_text(item, 320).strip()]
    return answer


__all__ = [
    "ANSWER_GENERATION_SCHEMA_VERSION",
    "fallback_answer_generation_evidence",
    "project_answer_generation_evidence",
]
