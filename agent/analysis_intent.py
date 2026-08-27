"""Domain-neutral, bounded analysis intent contract.

An analysis intent describes *what kind of analysis* a request needs.  It is
not a tool call and it does not select a Domain workflow.  Domain Packs may
project their own request facts into this contract; the Runtime only validates
the shape before carrying it to a Planner.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent.data_kinds import DataProfileError, normalize_data_kinds


ANALYSIS_INTENT_SCHEMA_VERSION = "spatial-agent.analysis-intent.v1"
SUPPORTED_ANALYSIS_OPERATIONS = (
    "query",
    "filter",
    "aggregate",
    "trend",
    "compare",
    "spatial_operation",
    "evidence",
)
MAX_OPERATIONS = 8
MAX_FACT_REFS = 16
MAX_OPERATION_KINDS = 8
MAX_TEXT = 96

_TOP_LEVEL_FIELDS = {
    "schema_version",
    "operations",
    "data_kinds",
    "fact_refs",
    "source",
}
_OPERATION_FIELDS = {
    "id",
    "kind",
    "operation",
    "type",
    "depends_on",
    "input_kinds",
    "output_kinds",
    "data_kinds",
    "fact_refs",
}
_OPERATION_ALIASES = {"operation": "kind", "type": "kind"}
_OPERATION_ALIASES_BY_VALUE = {
    "select": "query",
    "read": "query",
    "where": "filter",
    "group": "aggregate",
    "group_by": "aggregate",
    "time_series": "trend",
    "timeseries": "trend",
    "comparison": "compare",
    "spatial": "spatial_operation",
    "spatial_analysis": "spatial_operation",
    "source": "evidence",
    "provenance": "evidence",
}
_SOURCES = {"domain", "planner", "request", "replay", "unknown"}


class AnalysisIntentError(ValueError):
    """An analysis intent cannot be safely normalized."""

    def __init__(self, message: str, *, code: str = "analysis_intent_invalid"):
        self.code = str(code)[:MAX_TEXT]
        super().__init__(str(message)[:320])


def normalize_analysis_intent(
    value: Any,
    *,
    max_operations: int = MAX_OPERATIONS,
    max_fact_refs: int = MAX_FACT_REFS,
) -> dict[str, Any]:
    """Normalize and validate a bounded intent without interpreting a Domain.

    The returned object is JSON-safe and contains only operation vocabulary,
    data-kind identifiers and fact references.  Unknown fields, operations,
    data kinds, duplicate operation IDs and dependency cycles fail closed.
    """

    source = _mapping(value, "analysis_intent_object_required")
    _check_fields(source, _TOP_LEVEL_FIELDS, "analysis_intent_field_invalid")
    version = _text(source.get("schema_version"))
    if version and version != ANALYSIS_INTENT_SCHEMA_VERSION:
        raise AnalysisIntentError(
            "analysis intent schema is unsupported",
            code="analysis_intent_schema_invalid",
        )
    operation_limit = _positive_limit(max_operations, "max_operations")
    fact_limit = _positive_limit(max_fact_refs, "max_fact_refs")
    raw_operations = source.get("operations")
    if not isinstance(raw_operations, (list, tuple)) or not raw_operations:
        raise AnalysisIntentError(
            "analysis intent operations must be a non-empty array",
            code="analysis_intent_operations_required",
        )
    if len(raw_operations) > operation_limit:
        raise AnalysisIntentError(
            "analysis intent operations exceed the maximum",
            code="analysis_intent_operations_limit",
        )

    operations: list[dict[str, Any]] = []
    operation_ids: set[str] = set()
    for index, raw in enumerate(raw_operations):
        operation = _normalize_operation(raw, index=index, fact_limit=fact_limit)
        operation_id = operation["id"]
        if operation_id in operation_ids:
            raise AnalysisIntentError(
                "analysis intent operation IDs must be unique",
                code="analysis_intent_duplicate_operation",
            )
        operation_ids.add(operation_id)
        operations.append(operation)

    for operation in operations:
        dependencies = operation["depends_on"]
        if operation["id"] in dependencies:
            raise AnalysisIntentError(
                "analysis intent operation cannot depend on itself",
                code="analysis_intent_self_dependency",
            )
        if any(item not in operation_ids for item in dependencies):
            raise AnalysisIntentError(
                "analysis intent dependency is unknown",
                code="analysis_intent_dependency_unknown",
            )
    _assert_acyclic(operations)

    try:
        data_kinds = normalize_data_kinds(source.get("data_kinds", ["unknown"]))
    except DataProfileError as exc:
        raise AnalysisIntentError(
            "analysis intent data kinds are invalid",
            code="analysis_intent_data_kind_invalid",
        ) from exc
    source_name = _text(source.get("source")) or "unknown"
    if source_name not in _SOURCES:
        source_name = "unknown"
    return {
        "schema_version": ANALYSIS_INTENT_SCHEMA_VERSION,
        "operations": operations,
        "data_kinds": data_kinds,
        "fact_refs": _strings(source.get("fact_refs"), fact_limit),
        "source": source_name,
    }


def _normalize_operation(
    raw: Any,
    *,
    index: int,
    fact_limit: int,
) -> dict[str, Any]:
    if isinstance(raw, str):
        source: Mapping[str, Any] = {"kind": raw}
    elif isinstance(raw, Mapping):
        source = raw
    else:
        raise AnalysisIntentError(
            "analysis intent operation must be a string or object",
            code="analysis_intent_operation_invalid",
        )
    _check_fields(source, _OPERATION_FIELDS, "analysis_intent_operation_field_invalid")
    normalized: dict[str, Any] = {}
    for key, item in source.items():
        target = _OPERATION_ALIASES.get(str(key), str(key))
        if target in normalized:
            raise AnalysisIntentError(
                "analysis intent operation has conflicting aliases",
                code="analysis_intent_operation_alias_conflict",
            )
        normalized[target] = item
    kind = _normalize_kind(normalized.get("kind"))
    operation_id = _text(normalized.get("id")) or kind
    if not operation_id:
        operation_id = f"op-{index + 1}"
    operation_id = operation_id[:MAX_TEXT]
    depends_on = _strings(normalized.get("depends_on"), MAX_OPERATION_KINDS)
    input_kinds = _normalize_kinds(
        normalized.get("input_kinds"), code="analysis_intent_input_kind_invalid"
    )
    output_kinds = _normalize_kinds(
        normalized.get("output_kinds", normalized.get("data_kinds")),
        code="analysis_intent_output_kind_invalid",
        default=(),
    )
    return {
        "id": operation_id,
        "kind": kind,
        "depends_on": _unique(depends_on, MAX_OPERATION_KINDS),
        "input_kinds": input_kinds,
        "output_kinds": output_kinds,
        "fact_refs": _strings(normalized.get("fact_refs"), fact_limit),
    }


def _normalize_kind(value: Any) -> str:
    kind = _text(value).lower().replace("-", "_").replace(" ", "_")
    kind = _OPERATION_ALIASES_BY_VALUE.get(kind, kind)
    if kind not in SUPPORTED_ANALYSIS_OPERATIONS:
        raise AnalysisIntentError(
            "analysis intent operation is unsupported",
            code="analysis_intent_operation_unsupported",
        )
    return kind


def _normalize_kinds(value: Any, *, code: str, default: Sequence[str] | tuple = ()) -> list[str]:
    if value is None:
        return list(default)
    try:
        return normalize_data_kinds(value, allow_empty=True)[:MAX_OPERATION_KINDS]
    except DataProfileError as exc:
        raise AnalysisIntentError("analysis intent operation kinds are invalid", code=code) from exc


def _assert_acyclic(operations: Sequence[Mapping[str, Any]]) -> None:
    dependencies = {
        str(item.get("id")): set(item.get("depends_on") or ())
        for item in operations
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise AnalysisIntentError(
                "analysis intent dependencies contain a cycle",
                code="analysis_intent_dependency_cycle",
            )
        if node in visited:
            return
        visiting.add(node)
        for dependency in dependencies.get(node, ()):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in dependencies:
        visit(node)


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AnalysisIntentError("analysis intent must be an object", code=code)
    return value


def _check_fields(value: Mapping[str, Any], allowed: set[str], code: str) -> None:
    unknown = sorted(str(key) for key in value if str(key) not in allowed)
    if unknown:
        raise AnalysisIntentError("analysis intent contains unsupported fields", code=code)


def _positive_limit(value: Any, name: str) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise AnalysisIntentError(f"{name} must be positive", code="analysis_intent_limit_invalid") from exc
    if limit < 1:
        raise AnalysisIntentError(f"{name} must be positive", code="analysis_intent_limit_invalid")
    return min(limit, 64)


def _strings(value: Any, limit: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, (list, tuple, set)):
        raise AnalysisIntentError("analysis intent references must be an array", code="analysis_intent_reference_invalid")
    return _unique([_text(item) for item in list(value)[:limit] if _text(item)], limit)


def _unique(values: Sequence[str], limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result and len(result) < limit:
            result.append(value[:MAX_TEXT])
    return result


def _text(value: Any) -> str:
    return str(value or "").strip()[:MAX_TEXT]


__all__ = [
    "ANALYSIS_INTENT_SCHEMA_VERSION",
    "SUPPORTED_ANALYSIS_OPERATIONS",
    "MAX_OPERATIONS",
    "MAX_FACT_REFS",
    "AnalysisIntentError",
    "normalize_analysis_intent",
]
