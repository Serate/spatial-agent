"""Domain-neutral contract helpers for bounded record analysis."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


RECORD_ANALYSIS_SCHEMA_VERSION = "spatial-agent.record-analysis.v1"
RECORD_OPERATIONS = ("filter", "aggregate", "timeseries", "compare")
RECORD_FILTER_OPERATORS = ("eq", "neq", "gt", "gte", "lt", "lte", "in")
RECORD_AGGREGATIONS = ("count", "sum", "mean", "min", "max")
RECORD_MAX_CONDITIONS = 32
RECORD_MAX_GROUP_FIELDS = 8
RECORD_MAX_AGGREGATIONS = 8
RECORD_MAX_LIMIT = 10_000


class RecordContractError(ValueError):
    """A record-analysis request is not valid at the provider seam."""

    def __init__(self, message: str, *, code: str = "record_query_invalid"):
        self.code = str(code)[:96]
        super().__init__(message)


def normalize_record_request(
    *,
    operation: Any,
    filters: Any = (),
    group_by: Any = (),
    aggregations: Any = (),
    time_field: Any = None,
    limit: Any = 256,
) -> dict[str, Any]:
    """Normalize a ToolRegistry-shaped request without interpreting domains."""

    operation_text = str(operation or "").strip().lower()
    if operation_text not in RECORD_OPERATIONS:
        raise RecordContractError("unsupported record analysis operation")
    normalized_filters = _conditions(filters)
    normalized_groups = _field_list(group_by, "group_by", RECORD_MAX_GROUP_FIELDS)
    normalized_aggregations = _aggregations(aggregations)
    normalized_time_field = _field_name(time_field, "time_field", required=False)
    try:
        normalized_limit = int(limit)
    except (TypeError, ValueError):
        raise RecordContractError("record analysis limit must be an integer") from None
    if normalized_limit < 1 or normalized_limit > RECORD_MAX_LIMIT:
        raise RecordContractError("record analysis limit is outside the allowed range")
    if operation_text == "timeseries" and not normalized_time_field:
        raise RecordContractError(
            "timeseries analysis requires time_field",
            code="record_time_field_required",
        )
    if operation_text == "compare" and not normalized_groups:
        raise RecordContractError(
            "compare analysis requires group_by",
            code="record_group_by_required",
        )
    return {
        "operation": operation_text,
        "filters": normalized_filters,
        "group_by": normalized_groups,
        "aggregations": normalized_aggregations,
        "time_field": normalized_time_field,
        "limit": normalized_limit,
    }


def _conditions(value: Any) -> list[dict[str, Any]]:
    if value in (None, ()):
        return []
    if not isinstance(value, (list, tuple)):
        raise RecordContractError("record analysis filters must be an array")
    if len(value) > RECORD_MAX_CONDITIONS:
        raise RecordContractError("record analysis has too many filters")
    result = []
    for item in value:
        if not isinstance(item, Mapping):
            raise RecordContractError("record analysis filter must be an object")
        field = _field_name(item.get("field"), "filter.field")
        operator = str(item.get("operator") or "").strip().lower()
        if operator not in RECORD_FILTER_OPERATORS:
            raise RecordContractError("unsupported record analysis filter operator")
        if "value" not in item:
            raise RecordContractError("record analysis filter value is required")
        value_item = item.get("value")
        if operator == "in":
            if not isinstance(value_item, (list, tuple, set)) or not value_item:
                raise RecordContractError("in filter value must be a non-empty array")
            value_item = list(value_item)[:64]
        result.append({"field": field, "operator": operator, "value": value_item})
    return result


def _aggregations(value: Any) -> list[dict[str, Any]]:
    if value in (None, ()):
        return []
    if not isinstance(value, (list, tuple)):
        raise RecordContractError("record analysis aggregations must be an array")
    if len(value) > RECORD_MAX_AGGREGATIONS:
        raise RecordContractError("record analysis has too many aggregations")
    result = []
    aliases = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise RecordContractError("record analysis aggregation must be an object")
        function = str(item.get("function") or "").strip().lower()
        if function not in RECORD_AGGREGATIONS:
            raise RecordContractError("unsupported record analysis aggregation")
        alias = _field_name(item.get("alias"), "aggregation.alias")
        if alias in aliases:
            raise RecordContractError("record analysis aggregation aliases must be unique")
        aliases.add(alias)
        field = _field_name(item.get("field"), "aggregation.field", required=False)
        if function != "count" and not field:
            raise RecordContractError("numeric aggregation requires field")
        result.append({"function": function, "field": field, "alias": alias})
    return result


def _field_list(value: Any, name: str, limit: int) -> list[str]:
    if value in (None, ()):
        return []
    if not isinstance(value, (list, tuple)):
        raise RecordContractError(name + " must be an array")
    if len(value) > limit:
        raise RecordContractError(name + " has too many fields")
    result = []
    for item in value:
        field = _field_name(item, name)
        if field not in result:
            result.append(field)
    return result


def _field_name(value: Any, name: str, *, required: bool = True) -> str | None:
    if value in (None, "") and not required:
        return None
    text = str(value or "").strip()
    if not text:
        raise RecordContractError(name + " is required")
    return text[:96]


__all__ = [
    "RECORD_ANALYSIS_SCHEMA_VERSION",
    "RECORD_OPERATIONS",
    "RECORD_FILTER_OPERATORS",
    "RECORD_AGGREGATIONS",
    "RecordContractError",
    "normalize_record_request",
]
