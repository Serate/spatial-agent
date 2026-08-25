"""Reusable analysis engine for normalized numeric observations.

Domain adapters own loading, source validation and domain vocabulary.  This
module owns the repeated table-analysis semantics: catalog aggregation,
period filtering, latest/trend/compare projections and source de-duplication.
It deliberately has no knowledge of a particular domain, dataset path or
request parser.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Mapping, Sequence

from agent.data_kinds import build_data_profile

from .record_analysis import RecordAnalysisEngine


@dataclass(frozen=True)
class IndicatorAnalysisConfig:
    """Small policy object for domain compatibility at the analysis seam."""

    result_prefix: str = "indicator"
    status_codes: Mapping[str, str] = field(default_factory=dict)
    retryable_codes: tuple[str, ...] = ()
    max_rows: int = 256
    max_sources: int = 32
    include_source_evidence: bool = False
    include_source_record_count: bool = False
    include_geography_levels: bool = False
    include_period_type: bool = False
    mean_digits: int | None = None


class IndicatorAnalysisEngine:
    """Deep module hiding common indicator/table analysis behavior."""

    def __init__(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        dataset_id: str,
        provenance: Mapping[str, Any] | None = None,
        config: IndicatorAnalysisConfig | None = None,
    ) -> None:
        self._records = [dict(record) for record in records if isinstance(record, Mapping)]
        self._dataset_id = str(dataset_id)[:96]
        self._provenance = {
            str(key): str(value)[:512]
            for key, value in (provenance or {}).items()
            if value is not None
        }
        self._config = config or IndicatorAnalysisConfig()
        self._record_engine = RecordAnalysisEngine(
            dataset_id=self._dataset_id,
            provenance=self._provenance,
            max_output=self._config.max_rows,
        )

    def list_indicators(self) -> dict[str, Any]:
        """Return a bounded catalog derived only from normalized records."""

        if not self._records:
            return self._status_result("unavailable", self._code("data_unavailable")) | {
                "indicators": [],
                "regions": [],
                "periods": [],
                "period_types": [],
            }

        indicators: dict[str, dict[str, Any]] = {}
        for record in self._records:
            indicator_id = str(record.get("indicator") or "")
            if not indicator_id:
                continue
            entry = indicators.setdefault(
                indicator_id,
                {
                    "id": indicator_id,
                    "label": str(record.get("label") or indicator_id),
                    "units": set(),
                    "geography_levels": set(),
                    "period_types": set(),
                    "periods": set(),
                },
            )
            for key in ("unit", "geography_level", "period_type", "period"):
                value = record.get(key)
                if value not in (None, ""):
                    field_name = {
                        "unit": "units",
                        "geography_level": "geography_levels",
                        "period_type": "period_types",
                        "period": "periods",
                    }[key]
                    entry[field_name].add(str(value))

        values = []
        for item in indicators.values():
            values.append(
                {
                    "id": item["id"],
                    "label": item["label"],
                    "units": sorted(item["units"]),
                    "geography_levels": sorted(item["geography_levels"]),
                    "period_types": sorted(item["period_types"]),
                    "periods": sorted(item["periods"], key=_period_key),
                }
            )
        return {
            "status": "ready",
            "indicators": values[:64],
            "regions": sorted({str(item["region"]) for item in self._records if item.get("region")})[:128],
            "periods": sorted(
                {str(item["period"]) for item in self._records if item.get("period")},
                key=_period_key,
            )[:128],
            "period_types": sorted(
                {str(item["period_type"]) for item in self._records if item.get("period_type")}
            )[:16],
            "provenance": dict(self._provenance),
            "data_profile": build_data_profile(("metrics",)),
        }

    def query(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Execute latest, trend or compare over bounded observations."""

        if not self._records:
            return self._status_result("unavailable", self._code("data_unavailable"), arguments)

        operation = str(arguments.get("operation") or "latest")
        indicator = str(arguments.get("indicator") or "").strip()
        regions = _regions(arguments.get("regions"))
        period_type = str(arguments.get("period_type") or "").strip()
        start = str(arguments.get("period_start") or "").strip()
        end = str(arguments.get("period_end") or "").strip()

        known_indicators = {str(item.get("indicator")) for item in self._records}
        if indicator not in known_indicators:
            return self._status_result("unavailable", self._code("indicator_unavailable"), arguments)

        known_regions = {str(item.get("region")) for item in self._records}
        missing_regions = [region for region in regions if region not in known_regions]
        if missing_regions:
            result = self._status_result("unavailable", self._code("region_unavailable"), arguments)
            result["missing_regions"] = missing_regions[:16]
            return result

        records = self._filter(indicator, regions, period_type, start, end)
        if not records:
            code_key = "time_range_unavailable" if period_type or start or end else "data_not_found"
            return self._status_result("unavailable", self._code(code_key), arguments)

        records.sort(key=lambda item: (str(item.get("region")), _period_key(item.get("period"))))
        if operation == "latest":
            rows = self._latest_by_region(records)
            profile = ("metrics",)
            result_type = f"{self._config.result_prefix}_metrics_result"
        elif operation == "compare":
            rows = self._latest_by_region(records)
            profile = ("composite", "metrics")
            result_type = f"{self._config.result_prefix}_comparison_result"
        else:
            rows = records
            profile = ("timeseries", "metrics")
            result_type = f"{self._config.result_prefix}_timeseries_result"

        numeric = [
            float(item["value"])
            for item in rows
            if isinstance(item.get("value"), (int, float)) and not isinstance(item.get("value"), bool)
        ]
        metrics: dict[str, Any] = {
            "record_count": len(rows),
            "region_count": len({str(item.get("region")) for item in rows}),
            "minimum": min(numeric) if numeric else None,
            "maximum": max(numeric) if numeric else None,
            "mean": self._mean(numeric),
        }
        if self._config.include_source_record_count:
            metrics["source_record_count"] = len(records)
        if self._config.include_geography_levels:
            metrics["geography_levels"] = sorted(
                {str(item.get("geography_level") or "unknown") for item in rows}
            )
        if self._config.include_period_type:
            metrics["period_type"] = period_type or str(records[0].get("period_type") or "unknown")
        if operation == "trend":
            by_region: dict[str, list[dict[str, Any]]] = {}
            for item in records:
                by_region.setdefault(str(item.get("region")), []).append(item)
            metrics["changes"] = {
                region: self._round(float(values[-1]["value"]) - float(values[0]["value"]))
                for region, values in by_region.items()
                if len(values) >= 2
            }

        result = {
            "status": "ready",
            "result_type": result_type,
            "operation": operation,
            "dataset": self._dataset_id,
            "indicator": indicator,
            "rows": deepcopy(rows[: max(1, int(self._config.max_rows))]),
            "metrics": metrics,
            "data_profile": build_data_profile(profile),
            "provenance": dict(self._provenance),
        }
        if self._config.include_source_evidence:
            result["source_evidence"] = self._source_entries(rows)
        return result

    def source_evidence(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Return source entries using the same filter as :meth:`query`."""

        if not self._records:
            return self._status_result("unavailable", self._code("data_unavailable"), arguments)
        indicator = str(arguments.get("indicator") or "").strip()
        regions = _regions(arguments.get("regions"))
        period_type = str(arguments.get("period_type") or "").strip()
        start = str(arguments.get("period_start") or "").strip()
        end = str(arguments.get("period_end") or "").strip()
        rows = self._filter(indicator, regions, period_type, start, end)
        if not rows:
            return self._status_result(
                "unavailable",
                self._code("source_evidence_unavailable"),
                arguments,
            )
        return {
            "status": "ready",
            "dataset": self._dataset_id,
            "indicator": indicator,
            "sources": self._source_entries(rows),
            "data_profile": build_data_profile(("document_evidence",)),
            "provenance": dict(self._provenance),
        }

    def _filter(
        self,
        indicator: str,
        regions: Sequence[str],
        period_type: str,
        start: str,
        end: str,
    ) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = [
            {"field": "indicator", "operator": "eq", "value": indicator},
            {"field": "region", "operator": "in", "value": list(regions)},
        ]
        if period_type:
            filters.append({"field": "period_type", "operator": "eq", "value": period_type})
        result = self._record_engine.analyze(
            self._records,
            operation="filter",
            filters=filters,
            limit=self._config.max_rows,
        )
        rows = [dict(item) for item in result.get("rows", []) if isinstance(item, Mapping)]
        start_key = _period_key(start) if start else None
        end_key = _period_key(end) if end else None
        if start_key is not None:
            rows = [item for item in rows if _period_key(item.get("period")) >= start_key]
        if end_key is not None:
            rows = [item for item in rows if _period_key(item.get("period")) <= end_key]
        return rows

    def _status_result(
        self,
        status: str,
        code: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        args = dict(arguments or {})
        return {
            "status": status,
            "code": code,
            "retryable": code in set(self._config.retryable_codes),
            "dataset": self._dataset_id,
            "requested": {
                "indicator": str(args.get("indicator") or ""),
                "regions": _regions(args.get("regions"))[:16],
                "period_type": str(args.get("period_type") or ""),
                "period_start": str(args.get("period_start") or ""),
                "period_end": str(args.get("period_end") or ""),
            },
            "rows": [],
            "metrics": {},
            "data_profile": build_data_profile(("metrics",)),
            "provenance": dict(self._provenance),
        }

    def _source_entries(self, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            source = row.get("source")
            if not isinstance(source, Mapping):
                continue
            key = (
                str(source.get("url") or ""),
                str(source.get("version") or ""),
                str(source.get("locator") or ""),
            )
            unique[key] = {
                str(name): str(source[name])[:512]
                for name in (
                    "name",
                    "url",
                    "published_at",
                    "retrieved_at",
                    "version",
                    "license",
                    "locator",
                    "geography_level",
                )
                if source.get(name) is not None
            }
        return list(unique.values())[: max(1, int(self._config.max_sources))]

    def _code(self, key: str) -> str:
        return str(self._config.status_codes.get(key) or f"{self._config.result_prefix}_{key}")[:96]

    def _mean(self, values: Sequence[float]) -> float | None:
        if not values:
            return None
        return self._round(mean(values))

    def _round(self, value: float) -> float:
        digits = self._config.mean_digits
        return round(value, digits) if digits is not None else value

    @staticmethod
    def _latest_by_region(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for item in records:
            key = str(item.get("region"))
            if key not in latest or _period_key(item.get("period")) > _period_key(latest[key].get("period")):
                latest[key] = dict(item)
        return [latest[key] for key in sorted(latest)]


def _regions(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _period_key(value: Any) -> tuple[int, int, int, str]:
    text = str(value or "")
    digits = "".join(char if char.isdigit() else " " for char in text).split()
    year = int(digits[0]) if digits else -1
    suffix = text.upper()
    if "H" in suffix:
        part = 1 if suffix.endswith("H1") else 2
        return year, 2, part, text
    if "Q" in suffix:
        part = int(digits[1]) if len(digits) > 1 else 0
        return year, 1, part, text
    return year, 0, 0, text
