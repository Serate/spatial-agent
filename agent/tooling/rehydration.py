"""Safe restart rehydration for approved dynamic tools.

The approval store is durable, while Registry handlers are intentionally
volatile.  This module joins the two only through public approval identity:
the handler factory receives ``proposal_id`` and ``source_hash`` and the
Registry remains the only publication boundary.  No persisted source is read
or executed here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Callable

from agent.errors import ToolError


TOOL_REHYDRATION_SCHEMA_VERSION = "spatial-agent.tool-rehydration.v1"
_MAX_RECORDS = 64
_MAX_TEXT = 128


def rehydrate_approved_tools(
    *,
    registry: Any,
    records: Iterable[Any],
    handler_factory: Callable[[Mapping[str, Any]], Any] | None,
    domain_id: str,
) -> dict[str, Any]:
    """Rebind approved records through the Registry and return safe evidence.

    Every non-bound outcome is represented as ``degraded`` or ``skipped``;
    one malformed record cannot prevent the Runtime from starting.  The
    returned projection deliberately excludes definitions, source, examples,
    prompts and model output.
    """

    normalized_domain = _text(domain_id, "unknown")
    bindings: list[dict[str, Any]] = []
    degraded: list[dict[str, Any]] = []
    skipped = 0
    attempted = 0
    if not callable(getattr(registry, "register_approved_tool", None)):
        return _summary(
            normalized_domain,
            attempted=0,
            skipped=0,
            bindings=[],
            degraded=[_outcome({}, state="degraded", reason="registry_unavailable")],
        )

    for item in list(records or [])[:_MAX_RECORDS]:
        public = _public_record(item)
        if not public:
            skipped += 1
            continue
        if _text(public.get("domain_id"), "") != normalized_domain:
            skipped += 1
            continue
        if public.get("status") != "approved":
            skipped += 1
            continue
        attempted += 1
        base = _outcome(public, state="degraded", reason="handler_unavailable")
        if not callable(handler_factory):
            degraded.append(base)
            continue
        try:
            handler = handler_factory(public)
        except Exception:
            handler = None
        if not callable(handler):
            degraded.append(base)
            continue
        try:
            registered = registry.register_approved_tool(public, handler)
        except ToolError as exc:
            degraded.append(
                _outcome(
                    public,
                    state="degraded",
                    reason=_text(getattr(exc, "code", None), "registry_binding_rejected"),
                )
            )
            continue
        except Exception:
            degraded.append(
                _outcome(public, state="degraded", reason="registry_binding_rejected")
            )
            continue
        bindings.append(
            _outcome(
                public,
                state="bound",
                reason="approval_binding_restored",
                registration=registered,
            )
        )
    return _summary(
        normalized_domain,
        attempted=attempted,
        skipped=skipped,
        bindings=bindings,
        degraded=degraded,
    )


def _public_record(item: Any) -> dict[str, Any]:
    try:
        value = item.as_dict() if callable(getattr(item, "as_dict", None)) else item
    except Exception:
        return {}
    if not isinstance(value, Mapping):
        return {}
    # Copy only fields consumed by the Registry and the handler factory.  The
    # definition is bounded by ToolApprovalRecord.as_dict and never contains
    # proposal source, but is kept private to this function call.
    keys = (
        "schema_version",
        "approval_id",
        "proposal_id",
        "name",
        "domain_id",
        "run_id",
        "receipt_fingerprint",
        "source_hash",
        "schema_hash",
        "proposal_version",
        "status",
        "version",
        "reason_code",
        "definition",
    )
    return {key: value[key] for key in keys if key in value}


def _outcome(
    value: Mapping[str, Any],
    *,
    state: str,
    reason: str,
    registration: Any = None,
) -> dict[str, Any]:
    result = {
        "approval_id": _text(value.get("approval_id"), "unknown"),
        "name": _text(value.get("name"), "unknown"),
        "status": _text(value.get("status"), "unknown"),
        "version": _bounded_int(value.get("version")),
        "receipt_fingerprint": _text(value.get("receipt_fingerprint"), ""),
        "state": state,
        "reason_code": _text(reason, "rehydration_unavailable"),
    }
    if isinstance(registration, Mapping):
        result["handler_ref"] = _text(registration.get("handler_ref"), "")
    return result


def _summary(
    domain_id: str,
    *,
    attempted: int,
    skipped: int,
    bindings: list[dict[str, Any]],
    degraded: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": TOOL_REHYDRATION_SCHEMA_VERSION,
        "domain_id": domain_id,
        "state": "degraded" if degraded else "ready",
        "attempted": max(0, int(attempted)),
        "skipped": max(0, int(skipped)),
        "bound_count": len(bindings),
        "degraded_count": len(degraded),
        "bindings": bindings[:_MAX_RECORDS],
        "degraded": degraded[:_MAX_RECORDS],
    }


def _text(value: Any, fallback: str) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return fallback
    return str(value).replace("\x00", " ").strip()[:_MAX_TEXT] or fallback


def _bounded_int(value: Any) -> int:
    try:
        return max(0, min(2**31 - 1, int(value)))
    except (TypeError, ValueError, OverflowError):
        return 0


__all__ = ["TOOL_REHYDRATION_SCHEMA_VERSION", "rehydrate_approved_tools"]
