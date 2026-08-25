"""Deep, domain-neutral analysis of bounded mapping records.

Providers own I/O, schema discovery and domain provenance.  This module owns
only the reusable record semantics behind a deliberately small ``analyze``
interface.  It never imports a Domain Pack or opens a file/network client.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from agent.data_kinds import build_data_profile

from .record_contract import (
    RECORD_ANALYSIS_SCHEMA_VERSION,
    RecordContractError,
    normalize_record_request,
)


_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "credentials",
    "password",
    "secret",
    "token",
    "geometry",
    "coordinates",
    "features",
    "path",
    "file_path",
    "dataset_path",
}
_MAX_INPUT = 10_000
_MAX_OUTPUT = 256
_MAX_GROUPS = 128
_MAX_FIELDS = 64
_MAX_DEPTH = 4
_MAX_STRING = 512


class RecordAnalysisEngine:
    """Analyze records through one bounded, domain-neutral interface."""

    def __init__(
        self,
        *,
        dataset_id: str,
        provenance: Mapping[str, Any] | None = None,
        max_input: int = _MAX_INPUT,
        max_output: int = _MAX_OUTPUT,
        max_groups: int = _MAX_GROUPS,
    ) -> None:
        self._dataset_id = str(dataset_id or "unknown")[:96]
        self._provenance = _safe_mapping(provenance or {})
        self._max_input = max(1, min(int(max_input), _MAX_INPUT))
        self._max_output = max(1, min(int(max_output), _MAX_OUTPUT))
        self._max_groups = max(1, min(int(max_groups), _MAX_GROUPS))

    def analyze(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        operation: Any,
        filters: Any = (),
        group_by: Any = (),
        aggregations: Any = (),
        time_field: Any = None,
        limit: Any = 256,
    ) -> dict[str, Any]:
        try:
            request = normalize_record_request(
                operation=operation,
                filters=filters,
                group_by=group_by,
                aggregations=aggregations,
                time_field=time_field,
                limit=limit,
            )
        except RecordContractError as exc:
            return self._failure(exc.code, str(exc), request={})

        source = [dict(item) for item in list(records or []) if isinstance(item, Mapping)]
        if not source:
            return self._failure(
                "record_data_unavailable",
                "record analysis data is unavailable",
                request=request,
            )
        input_count = len(source)
        truncated_input = input_count > self._max_input
        source = source[: self._max_input]
        fields = {str(key) for row in source for key in row.keys()}
        referenced = {
            item["field"]
            for item in request["filters"]
        }
        referenced.update(request["group_by"])
        if request["time_field"]:
            referenced.add(request["time_field"])
        for item in request["aggregations"]:
            if item.get("field"):
                referenced.add(item["field"])
        missing = sorted(field for field in referenced if field not in fields)
        if missing:
            return self._failure(
                "record_field_mismatch",
                "record analysis requested fields are unavailable",
                request=request,
                extra={"missing_fields": missing[:16]},
            )

        filtered = [row for row in source if _matches_all(row, request["filters"])]
        if request["operation"] == "filter":
            output_rows = [_project_record(row) for row in filtered]
        else:
            try:
                output_rows = self._aggregate_rows(filtered, request)
            except RecordContractError as exc:
                return self._failure(
                    exc.code,
                    str(exc),
                    request=request,
                    extra={"missing_fields": [exc.args[1]]} if len(exc.args) > 1 else None,
                )

        output_limit = min(request["limit"], self._max_output)
        warnings = []
        if truncated_input:
            warnings.append("输入记录超过预算，仅分析前 {} 条。".format(self._max_input))
        if not filtered:
            warnings.append("没有记录满足当前筛选条件。")
        status = "degraded" if truncated_input else "ready"
        profile = {
            "filter": ("metrics",),
            "aggregate": ("metrics",),
            "timeseries": ("timeseries", "metrics"),
            "compare": ("composite", "metrics"),
        }[request["operation"]]
        metrics = {
            "input_count": input_count,
            "scanned_count": len(source),
            "filtered_count": len(filtered),
            "output_count": min(len(output_rows), output_limit),
            "group_count": len(output_rows) if request["operation"] != "filter" else 0,
            "truncated_input": truncated_input,
            "truncated_output": len(output_rows) > output_limit,
        }
        if len(output_rows) > output_limit:
            warnings.append("输出记录超过预算，结果已截断。")
        return {
            "schema_version": RECORD_ANALYSIS_SCHEMA_VERSION,
            "status": status,
            "result_type": "record_analysis_result",
            "operation": request["operation"],
            "dataset": self._dataset_id,
            "rows": deepcopy(output_rows[:output_limit]),
            "metrics": metrics,
            "data_profile": build_data_profile(profile),
            "provenance": deepcopy(self._provenance),
            "request": _safe_request(request),
            "warnings": warnings[:8],
        }

    def _aggregate_rows(
        self,
        records: Sequence[Mapping[str, Any]],
        request: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        group_fields = list(request["group_by"])
        time_field = request.get("time_field")
        if request["operation"] == "timeseries" and time_field not in group_fields:
            group_fields.append(time_field)
        grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
        if group_fields:
            for record in records:
                key = tuple(_hashable(record.get(field)) for field in group_fields)
                grouped[key].append(record)
        else:
            grouped[()] = list(records)

        if len(grouped) > self._max_groups:
            keys = sorted(grouped, key=_sort_key)[: self._max_groups]
            grouped = {key: grouped[key] for key in keys}
        definitions = list(request["aggregations"])
        if not definitions:
            definitions = [{"function": "count", "field": None, "alias": "count"}]
        rows = []
        for key, members in grouped.items():
            row = {
                field: _project_value(value)
                for field, value in zip(group_fields, key)
            }
            for definition in definitions:
                row[definition["alias"]] = self._aggregate_value(
                    members,
                    definition["function"],
                    definition.get("field"),
                )
            rows.append(row)
        if request["operation"] == "timeseries" and time_field:
            rows.sort(key=lambda item: (_time_key(item.get(time_field)), _sort_key(item)))
        else:
            rows.sort(key=_sort_key)
        return rows

    @staticmethod
    def _aggregate_value(
        records: Sequence[Mapping[str, Any]],
        function: str,
        field: str | None,
    ) -> Any:
        if function == "count":
            if not field:
                return len(records)
            return sum(1 for record in records if record.get(field) is not None)
        values = [record.get(field) for record in records]
        numeric = [
            float(value)
            for value in values
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        ]
        if len(numeric) != len([value for value in values if value is not None]):
            raise RecordContractError(
                "numeric aggregation requires numeric values",
                code="record_field_mismatch",
            )
        if not numeric:
            return None
        if function == "sum":
            return _number(sum(numeric))
        if function == "mean":
            return _number(sum(numeric) / len(numeric))
        if function == "min":
            return _number(min(numeric))
        if function == "max":
            return _number(max(numeric))
        raise RecordContractError("unsupported record analysis aggregation")

    def _failure(
        self,
        code: str,
        message: str,
        *,
        request: Mapping[str, Any],
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            "schema_version": RECORD_ANALYSIS_SCHEMA_VERSION,
            "status": "unavailable",
            "code": str(code)[:96],
            "retryable": False,
            "message": str(message)[:240],
            "result_type": "record_analysis_result",
            "dataset": self._dataset_id,
            "rows": [],
            "metrics": {},
            "data_profile": build_data_profile(("metrics",)),
            "provenance": deepcopy(self._provenance),
            "request": _safe_request(request),
            "warnings": [],
        }
        if isinstance(extra, Mapping):
            result.update({str(key)[:64]: _project_value(value) for key, value in extra.items()})
        return result


def _matches_all(record: Mapping[str, Any], conditions: Sequence[Mapping[str, Any]]) -> bool:
    return all(_matches(record.get(item["field"]), item["operator"], item["value"]) for item in conditions)


def _matches(actual: Any, operator: str, expected: Any) -> bool:
    try:
        if operator == "in":
            return any(_matches(actual, "eq", item) for item in expected)
        if operator == "eq":
            return actual == expected
        if operator == "neq":
            return actual != expected
        if operator == "gt":
            return actual > expected
        if operator == "gte":
            return actual >= expected
        if operator == "lt":
            return actual < expected
        if operator == "lte":
            return actual <= expected
    except (TypeError, ValueError):
        return False
    return False


def _project_record(record: Mapping[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in list(record.items())[:_MAX_FIELDS]:
        name = str(key)[:96]
        if _sensitive(name):
            continue
        projected = _project_value(value)
        if projected is not None:
            result[name] = projected
    return result


def _project_value(value: Any, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return "…"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, str):
        return value[:_MAX_STRING]
    if isinstance(value, Mapping):
        return {
            str(key)[:96]: _project_value(child, depth + 1)
            for key, child in list(value.items())[:_MAX_FIELDS]
            if not _sensitive(str(key))
        }
    if isinstance(value, (list, tuple, set)):
        return [_project_value(item, depth + 1) for item in list(value)[:32]]
    return str(value)[:_MAX_STRING]


def _safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return _project_value(value) if isinstance(_project_value(value), dict) else {}


def _safe_request(request: Mapping[str, Any]) -> dict[str, Any]:
    return _project_value(request) if isinstance(_project_value(request), dict) else {}


def _sensitive(value: str) -> bool:
    lowered = value.lower()
    return lowered in _SENSITIVE_KEYS or any(token in lowered for token in ("password", "secret", "token", "credential"))


def _hashable(value: Any) -> Any:
    projected = _project_value(value)
    if isinstance(projected, (dict, list)):
        return repr(projected)
    return projected


def _sort_key(value: Any) -> str:
    return repr(value)


def _time_key(value: Any) -> tuple[int, int, int, str]:
    text = str(value or "")
    digits = [int(item) for item in re.findall(r"\d+", text)[:3]]
    return (
        digits[0] if digits else -1,
        digits[1] if len(digits) > 1 else -1,
        digits[2] if len(digits) > 2 else -1,
        text,
    )


def _number(value: float) -> int | float | None:
    if not math.isfinite(float(value)):
        return None
    rounded = round(float(value), 6)
    return int(rounded) if rounded.is_integer() else rounded


__all__ = ["RecordAnalysisEngine"]
