"""Domain-neutral conversation turn identity and continuation policy."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, Dict, Optional

CONVERSATION_TURN_SCHEMA_VERSION = "spatial-agent.conversation-turn.v1"
TURN_MODES = frozenset(
    {"new_request", "clarification_reply", "follow_up", "decision_reply", "unknown"}
)


def resolve_turn_mode(
    domain_pack: Any,
    request: str,
    *,
    pending_request: Optional[str] = None,
    pending_error: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask the Domain whether a pending turn should consume this input.

    The Runtime owns the lifecycle transition; a Domain may only advise which
    interpretation fits its own request language. Older Domain Packs retain
    the historical clarification-reply behavior when the optional seam is
    absent.
    """

    has_pending = bool(str(pending_request or "").strip())
    default_mode = "clarification_reply" if has_pending else "new_request"
    method = getattr(domain_pack, "classify_conversation_turn", None)
    if not callable(method):
        return {
            "mode": default_mode,
            "source": "runtime_legacy",
            "pending": has_pending,
        }
    try:
        value = method(
            str(request or "").strip(),
            pending_request=str(pending_request or "").strip(),
            pending_error=str(pending_error or "")[:240],
        )
    except TypeError:
        try:
            value = method(str(request or "").strip(), str(pending_request or "").strip())
        except Exception:
            value = None
    except Exception:
        value = None
    if not isinstance(value, Mapping):
        return {
            "mode": default_mode,
            "source": "runtime_legacy",
            "pending": has_pending,
        }
    mode = str(value.get("mode") or default_mode).strip()
    if mode not in TURN_MODES:
        mode = default_mode
    if not has_pending and mode == "clarification_reply":
        mode = "new_request"
    return {
        "mode": mode,
        "source": str(value.get("source") or "domain")[:64],
        "reason_code": str(value.get("reason_code") or "")[:96],
        "pending": has_pending,
    }


def build_conversation_turn(
    request: str,
    resolved_request: str,
    *,
    session_id: str,
    mode: str,
    source: str = "runtime",
    pending_request: Optional[str] = None,
    pending_available: Optional[bool] = None,
    reason_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a bounded, portable turn projection for every transport."""

    normalized_mode = str(mode or "unknown")
    if normalized_mode not in TURN_MODES:
        normalized_mode = "unknown"
    pending = str(pending_request or "").strip()
    available = bool(pending) if pending_available is None else bool(pending_available)
    consumed = bool(pending) and normalized_mode in {
        "clarification_reply",
        "follow_up",
        "decision_reply",
    }
    result: Dict[str, Any] = {
        "schema_version": CONVERSATION_TURN_SCHEMA_VERSION,
        "mode": normalized_mode,
        "source": str(source or "runtime")[:64],
        "is_continuation": normalized_mode in {"clarification_reply", "follow_up", "decision_reply"},
        "pending_available": available,
        "pending_consumed": consumed,
        "request_fingerprint": _fingerprint(request),
        "resolved_request_fingerprint": _fingerprint(resolved_request),
        "session_fingerprint": _fingerprint(session_id),
    }
    if pending and consumed:
        result["parent_request_fingerprint"] = _fingerprint(pending)
    if reason_code:
        result["reason_code"] = str(reason_code)[:96]
    return result


def normalize_conversation_turn(value: Any) -> Dict[str, Any]:
    """Normalize a persisted turn without carrying request text or paths."""

    if not isinstance(value, Mapping):
        return {
            "schema_version": CONVERSATION_TURN_SCHEMA_VERSION,
            "available": False,
            "mode": "unknown",
            "is_continuation": False,
        }
    mode = str(value.get("mode") or "unknown")
    if mode not in TURN_MODES:
        mode = "unknown"
    normalized: Dict[str, Any] = {
        "schema_version": CONVERSATION_TURN_SCHEMA_VERSION,
        "available": True,
        "mode": mode,
        "source": str(value.get("source") or "unknown")[:64],
        "is_continuation": mode in {"clarification_reply", "follow_up", "decision_reply"},
        "pending_available": bool(value.get("pending_available")),
        "pending_consumed": bool(
            value.get("pending_consumed")
            or (
                value.get("mode") == "clarification_reply"
                and value.get("pending_available")
            )
        ),
    }
    for key in (
        "request_fingerprint",
        "resolved_request_fingerprint",
        "session_fingerprint",
        "parent_request_fingerprint",
        "reason_code",
    ):
        if value.get(key):
            normalized[key] = str(value[key])[:96]
    return normalized


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(str(value or "").strip().encode("utf-8")).hexdigest()[:32]


__all__ = [
    "CONVERSATION_TURN_SCHEMA_VERSION",
    "TURN_MODES",
    "build_conversation_turn",
    "normalize_conversation_turn",
    "resolve_turn_mode",
]
