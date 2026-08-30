"""Small, domain-neutral checks for user-visible answer quality.

The checker is deliberately conservative. It does not judge correctness by
inventing domain rules and it never receives prompts, provider payloads or
raw tool results. Its receipt is operational evidence, not a replacement
for the authoritative Result and Evidence contracts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


ANSWER_QUALITY_SCHEMA_VERSION = "spatial-agent.answer-quality.v1"
MAX_CHECKED_ANSWER_CHARS = 6000

_INTERNAL_MARKERS = (
    "memory://",
    "artifact://",
    "result_ref",
    "<|",
    "[object Object]",
    "object Object",
)
_GARBLED_MARKERS = ("\ufffd", "\\uFFFD")
_STATE_DISCLOSURE_TERMS = {
    "partial": ("部分", "未完成", "缺少", "不完整", "限制", "尚未"),
    "blocked": ("无法", "未能", "失败", "补充", "重试", "检查"),
    "waiting_decision": ("确认", "等待", "批准", "继续"),
    "pending": ("进行中", "处理中", "等待", "生成"),
}


def assess_answer(answer: Any, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a bounded, explainable quality receipt for a visible answer."""

    text = str(answer or "").strip()
    context = context if isinstance(context, Mapping) else {}
    state = _context_state(context)
    checks = {
        "non_empty": bool(text),
        "within_limit": len(text) <= MAX_CHECKED_ANSWER_CHARS,
        "no_internal_markers": not any(marker in text for marker in _INTERNAL_MARKERS),
        "readable_text": not any(marker in text for marker in _GARBLED_MARKERS),
        "state_disclosed": _state_disclosed(text, state),
    }
    reasons: list[str] = []
    if not checks["non_empty"]:
        reasons.append("answer_empty")
    if not checks["within_limit"]:
        reasons.append("answer_too_long")
    if not checks["no_internal_markers"]:
        reasons.append("answer_internal_marker")
    if not checks["readable_text"]:
        reasons.append("answer_unreadable")
    if state in _STATE_DISCLOSURE_TERMS and not checks["state_disclosed"]:
        reasons.append("answer_state_not_disclosed")
    hard_fail = not all(
        checks[name]
        for name in ("non_empty", "within_limit", "no_internal_markers", "readable_text")
    )
    status = "fail" if hard_fail else "warn" if reasons else "pass"
    return {
        "schema_version": ANSWER_QUALITY_SCHEMA_VERSION,
        "status": status,
        "answer_length": min(len(text), MAX_CHECKED_ANSWER_CHARS),
        "state": state or "complete",
        "checks": checks,
        "reason_codes": reasons[:6],
    }


def project_answer_quality(value: Any) -> dict[str, Any] | None:
    """Project only safe answer-quality receipt fields to public evidence."""

    if not isinstance(value, Mapping):
        return None
    status = str(value.get("status") or "unknown").strip().lower()
    if status not in {"pass", "warn", "fail", "unknown"}:
        status = "unknown"
    try:
        answer_length = max(0, min(MAX_CHECKED_ANSWER_CHARS, int(value.get("answer_length"))))
    except (TypeError, ValueError):
        answer_length = 0
    checks = value.get("checks")
    safe_checks = (
        {
            str(key)[:48]: bool(item)
            for key, item in list(checks.items())[:8]
            if isinstance(key, str) and isinstance(item, bool)
        }
        if isinstance(checks, Mapping)
        else {}
    )
    reasons = value.get("reason_codes")
    safe_reasons = (
        [str(item)[:64] for item in reasons[:6] if str(item).strip()]
        if isinstance(reasons, list)
        else []
    )
    return {
        "schema_version": ANSWER_QUALITY_SCHEMA_VERSION,
        "status": status,
        "answer_length": answer_length,
        "state": str(value.get("state") or "complete")[:32],
        "checks": safe_checks,
        "reason_codes": safe_reasons,
    }


def _context_state(context: Mapping[str, Any]) -> str:
    raw = context.get("state")
    if not raw:
        completeness = context.get("completeness")
        if isinstance(completeness, Mapping):
            raw = completeness.get("state")
    if not raw:
        raw = context.get("status")
    normalized = str(raw or "").strip().lower()
    aliases = {
        "completed": "complete",
        "success": "complete",
        "failed": "blocked",
        "error": "blocked",
        "waiting_for_decision": "waiting_decision",
        "awaiting_approval": "waiting_decision",
        "executing": "pending",
        "planning": "pending",
        "queued": "pending",
    }
    return aliases.get(normalized, normalized)


def _state_disclosed(answer: str, state: str) -> bool:
    if state in {"", "complete", "unavailable"}:
        return True
    return any(term in answer for term in _STATE_DISCLOSURE_TERMS.get(state, ()))


__all__ = [
    "ANSWER_QUALITY_SCHEMA_VERSION",
    "MAX_CHECKED_ANSWER_CHARS",
    "assess_answer",
    "project_answer_quality",
]
