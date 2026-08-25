"""Replaceable, source-bound provider for regional economic observations."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Mapping

from agent.data_kinds import build_data_profile
from agent.errors import ToolError

from .catalog import ECONOMIC_TOOL_DEFINITIONS


DEFAULT_DATA_FILENAME = "wuhan_hongshan_official.json"
REQUIRED_SOURCE_FIELDS = (
    "name",
    "url",
    "version",
    "retrieved_at",
    "locator",
    "geography_level",
)


class EconomicToolProvider:
    """Load normalized observations and expose bounded analytical operations.

    The provider deliberately does not scrape webpages at request time. A
    source adapter or an extraction job produces the normalized JSON, while
    this component validates its provenance and performs deterministic reads.
    """

    provider_id = "economic-source-bound"

    def __init__(self, data_path: str | None = None, *, default_root: str | Path | None = None):
        self._data_path = str(data_path or os.environ.get("SPATIAL_AGENT_ECONOMIC_DATA") or "")
        self._default_root = Path(default_root) if default_root else None
        self._payload = self._load_payload()
        self._validation_issues: list[dict[str, str]] = []
        self._records = self._normalize_records(self._payload.get("records"))
        raw_provenance = self._payload.get("provenance")
        self._provenance = {
            str(key): str(value)[:512]
            for key, value in (raw_provenance if isinstance(raw_provenance, Mapping) else {}).items()
            if key in {"source", "version", "attribution", "license", "retrieved_at"}
            and value is not None
        }

    def definitions(self) -> Mapping[str, Mapping[str, Any]]:
        return deepcopy(ECONOMIC_TOOL_DEFINITIONS)

    def health(self) -> Dict[str, Any]:
        status = "ready" if self._records and not self._validation_issues else "unavailable"
        return {
            "status": status,
            "data_readiness": status,
            "dataset": self._dataset_id(),
            "record_count": len(self._records),
            "validation_issue_count": len(self._validation_issues),
            "provenance": dict(self._provenance),
            "reason_code": self._availability_code() if status != "ready" else None,
        }

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "economic_list_indicators":
            return self._list_indicators()
        if name == "economic_indicator_query":
            return self._query(arguments)
        if name == "economic_source_evidence":
            return self._source_evidence(arguments)
        raise ToolError("unknown economic tool", code="unknown_economic_tool", retryable=False)

    def _list_indicators(self) -> Dict[str, Any]:
        indicators: dict[str, dict[str, Any]] = {}
        for item in self._records:
            indicator_id = str(item["indicator"])
            entry = indicators.setdefault(
                indicator_id,
                {
                    "id": indicator_id,
                    "label": str(item.get("label") or indicator_id),
                    "units": set(),
                    "geography_levels": set(),
                    "period_types": set(),
                    "periods": set(),
                },
            )
            if item.get("unit"):
                entry["units"].add(str(item["unit"]))
            if item.get("geography_level"):
                entry["geography_levels"].add(str(item["geography_level"]))
            if item.get("period_type"):
                entry["period_types"].add(str(item["period_type"]))
            if item.get("period"):
                entry["periods"].add(str(item["period"]))
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
        if not values:
            return self._status_result("unavailable", self._availability_code()) | {
                "indicators": [],
                "regions": [],
                "periods": [],
            }
        return {
            "status": "ready",
            "indicators": values[:64],
            "regions": sorted({str(item["region"]) for item in self._records})[:128],
            "periods": sorted({str(item["period"]) for item in self._records}, key=_period_key)[:128],
            "period_types": sorted({str(item["period_type"]) for item in self._records})[:16],
            "provenance": dict(self._provenance),
            "data_profile": build_data_profile(("metrics",)),
        }

    def _query(self, arguments: Mapping[str, Any]) -> Dict[str, Any]:
        operation = str(arguments.get("operation") or "latest")
        indicator = str(arguments.get("indicator") or "").strip()
        regions = [str(item).strip() for item in (arguments.get("regions") or []) if str(item).strip()]
        period_type = str(arguments.get("period_type") or "").strip()
        start = str(arguments.get("period_start") or "").strip()
        end = str(arguments.get("period_end") or "").strip()
        if not self._records:
            return self._status_result("unavailable", self._availability_code(), arguments)
        known_indicators = {str(item["indicator"]) for item in self._records}
        if indicator not in known_indicators:
            return self._status_result("unavailable", "economic_indicator_unavailable", arguments)
        known_regions = {str(item["region"]) for item in self._records}
        missing_regions = [region for region in regions if region not in known_regions]
        if missing_regions:
            result = self._status_result("unavailable", "economic_region_unavailable", arguments)
            result["missing_regions"] = missing_regions[:16]
            return result
        records = [
            dict(item)
            for item in self._records
            if str(item.get("indicator")) == indicator
            and str(item.get("region")) in regions
            and (not period_type or str(item.get("period_type")) == period_type)
            and (not start or _period_key(item.get("period")) >= _period_key(start))
            and (not end or _period_key(item.get("period")) <= _period_key(end))
        ]
        if not records:
            code = "economic_time_range_unavailable" if period_type or start or end else "economic_data_not_found"
            return self._status_result("unavailable", code, arguments)
        records.sort(key=lambda item: (str(item["region"]), _period_key(item["period"])))
        if operation == "latest":
            rows = self._latest_by_region(records)
            profile = build_data_profile(("metrics",))
            result_type = "economic_metrics_result"
        elif operation == "compare":
            rows = self._latest_by_region(records)
            profile = build_data_profile(("composite", "metrics"))
            result_type = "economic_comparison_result"
        else:
            rows = records
            profile = build_data_profile(("timeseries", "metrics"))
            result_type = "economic_timeseries_result"
        numeric = [float(item["value"]) for item in rows]
        by_region: dict[str, list[dict[str, Any]]] = {}
        for item in records:
            by_region.setdefault(str(item["region"]), []).append(item)
        metrics: dict[str, Any] = {
            "record_count": len(rows),
            "source_record_count": len(records),
            "region_count": len({str(item["region"]) for item in rows}),
            "geography_levels": sorted({str(item.get("geography_level") or "unknown") for item in rows}),
            "minimum": min(numeric) if numeric else None,
            "maximum": max(numeric) if numeric else None,
            "mean": round(mean(numeric), 6) if numeric else None,
            "period_type": period_type or str(records[0].get("period_type") or "unknown"),
        }
        if operation == "trend":
            metrics["changes"] = {
                region: round(float(values[-1]["value"]) - float(values[0]["value"]), 6)
                for region, values in by_region.items()
                if len(values) >= 2
            }
        return {
            "status": "ready",
            "result_type": result_type,
            "operation": operation,
            "dataset": self._dataset_id(),
            "indicator": indicator,
            "rows": rows[:512],
            "metrics": metrics,
            "data_profile": profile,
            "provenance": dict(self._provenance),
            "source_evidence": self._source_entries(rows),
        }

    def _source_evidence(self, arguments: Mapping[str, Any]) -> Dict[str, Any]:
        indicator = str(arguments.get("indicator") or "").strip()
        regions = [str(item).strip() for item in (arguments.get("regions") or []) if str(item).strip()]
        period_type = str(arguments.get("period_type") or "").strip()
        start = str(arguments.get("period_start") or "").strip()
        end = str(arguments.get("period_end") or "").strip()
        if not self._records:
            return self._status_result("unavailable", self._availability_code(), arguments)
        rows = [
            item
            for item in self._records
            if str(item.get("indicator")) == indicator
            and str(item.get("region")) in regions
            and (not period_type or str(item.get("period_type")) == period_type)
            and (not start or _period_key(item.get("period")) >= _period_key(start))
            and (not end or _period_key(item.get("period")) <= _period_key(end))
        ]
        if not rows:
            return self._status_result("unavailable", "economic_source_evidence_unavailable", arguments)
        return {
            "status": "ready",
            "dataset": self._dataset_id(),
            "indicator": indicator,
            "sources": self._source_entries(rows),
            "data_profile": build_data_profile(("document_evidence",)),
            "provenance": dict(self._provenance),
        }

    def _status_result(
        self,
        status: str,
        code: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        args = dict(arguments or {})
        return {
            "status": status,
            "code": code,
            "retryable": code in {"economic_data_unavailable", "economic_source_unverified"},
            "dataset": self._dataset_id(),
            "requested": {
                "indicator": str(args.get("indicator") or ""),
                "regions": list(args.get("regions") or [])[:16],
                "period_type": str(args.get("period_type") or ""),
            },
            "rows": [],
            "metrics": {},
            "data_profile": build_data_profile(("metrics",)),
            "provenance": dict(self._provenance),
        }

    def _source_entries(self, rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            source = row.get("source")
            if not isinstance(source, Mapping):
                continue
            key = (str(source.get("url") or ""), str(source.get("version") or ""), str(source.get("locator") or ""))
            unique[key] = {
                str(name): str(source[name])[:512]
                for name in ("name", "url", "published_at", "retrieved_at", "version", "license", "locator", "geography_level")
                if source.get(name) is not None
            }
        return list(unique.values())[:32]

    def _normalize_records(self, raw_records: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_records, list):
            return []
        records: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_records):
            if not isinstance(raw, Mapping):
                self._validation_issues.append({"record": str(index), "code": "record_not_object"})
                continue
            required = ("indicator", "label", "region_id", "region", "geography_level", "period", "period_type", "value", "unit", "source")
            missing = [name for name in required if raw.get(name) in (None, "")]
            source = raw.get("source")
            if not isinstance(source, Mapping):
                missing.append("source")
            else:
                missing.extend("source." + name for name in REQUIRED_SOURCE_FIELDS if source.get(name) in (None, ""))
            if missing or not isinstance(raw.get("value"), (int, float)) or isinstance(raw.get("value"), bool):
                self._validation_issues.append({"record": str(index), "code": "field_mismatch", "fields": ",".join(missing[:8])})
                continue
            row = dict(raw)
            row["value"] = float(raw["value"]) if isinstance(raw["value"], float) else int(raw["value"])
            row["period"] = str(raw["period"])[:32]
            row["period_type"] = str(raw["period_type"])[:32]
            row["source"] = {str(key): str(value)[:512] for key, value in source.items()}
            records.append(row)
        return records

    def _load_payload(self) -> Dict[str, Any]:
        path = self._resolve_path()
        if path is None:
            return {"provenance": {"source": "economic-data-not-configured"}, "records": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {"provenance": {"source": "economic-data-unreadable", "version": str(path)}, "records": []}
        return dict(payload) if isinstance(payload, Mapping) else {"records": []}

    def _resolve_path(self) -> Path | None:
        if self._data_path:
            return Path(self._data_path)
        roots = []
        if self._default_root:
            roots.append(self._default_root)
        configured_root = os.environ.get("SPATIAL_AGENT_DATASET_ROOT")
        if configured_root:
            roots.append(Path(configured_root))
        roots.extend((Path.cwd(), Path(__file__).resolve().parents[2]))
        for root in roots:
            candidate = root / "data" / "economic" / DEFAULT_DATA_FILENAME
            if candidate.is_file():
                return candidate
            candidate = root / "economic" / DEFAULT_DATA_FILENAME
            if candidate.is_file():
                return candidate
        return None

    def _dataset_id(self) -> str:
        return str(self._payload.get("dataset") or "wuhan_hongshan_economic_indicators")[:96]

    def _availability_code(self) -> str:
        if self._validation_issues:
            return "economic_field_mismatch"
        return "economic_data_unavailable"

    @staticmethod
    def _latest_by_region(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for item in records:
            key = str(item["region"])
            if key not in latest or _period_key(item["period"]) > _period_key(latest[key]["period"]):
                latest[key] = item
        return [latest[key] for key in sorted(latest)]


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
