"""Bounded, provider-neutral planning outcome matrix for acceptance harnesses."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


COMPOSITE_PLANNING_MATRIX_SCHEMA_VERSION = (
    "spatial-agent.composite-planning-matrix.v1"
)
_STATUSES = frozenset({"PLANNED", "NEEDS_CLARIFICATION", "REJECTED", "FAILED"})


def run_planning_outcome_matrix(
    cases: Sequence[Mapping[str, Any]],
    *,
    runner: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    """Run at most eight bounded cases and return only safe outcome receipts."""

    if not callable(runner):
        raise ValueError("runner must be callable")
    receipts: list[dict[str, Any]] = []
    for raw_case in list(cases or [])[:8]:
        if not isinstance(raw_case, Mapping):
            continue
        case_id = _safe_text(raw_case.get("id"), 96) or "case-{}".format(len(receipts) + 1)
        expected = _safe_status(raw_case.get("expected_status"))
        try:
            result = runner(raw_case)
            if not isinstance(result, Mapping):
                raise ValueError("planning result is not an object")
            status = _safe_status(result.get("status")) or "FAILED"
            error_code = _safe_text(result.get("error_code"), 96)
            components = result.get("components")
            component_count = len(components) if isinstance(components, list) else 0
            run_created = bool(_safe_text(result.get("run_id"), 160))
        except Exception as exc:
            status = "FAILED"
            error_code = _safe_text(getattr(exc, "code", None), 96) or "matrix_case_failed"
            component_count = 0
            run_created = False
        receipts.append(
            {
                "id": case_id,
                "expected_status": expected,
                "status": status,
                "error_code": error_code or None,
                "component_count": max(0, min(8, component_count)),
                "execution_run_created": run_created,
                "passed": bool(expected and expected == status and not run_created),
            }
        )
    return {
        "schema_version": COMPOSITE_PLANNING_MATRIX_SCHEMA_VERSION,
        "status": "passed" if receipts and all(item["passed"] for item in receipts) else "failed",
        "case_count": len(receipts),
        "cases": receipts,
    }


def _safe_status(value: Any) -> str:
    value = str(value or "").strip().upper()
    return value if value in _STATUSES else ""


def _safe_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


__all__ = [
    "COMPOSITE_PLANNING_MATRIX_SCHEMA_VERSION",
    "run_planning_outcome_matrix",
]
