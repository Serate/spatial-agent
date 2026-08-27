"""Replaceable, source-bound provider for regional economic observations."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping

from agent.analysis.indicator_core import IndicatorAnalysisConfig, IndicatorAnalysisEngine
from agent.errors import ToolError

from .catalog import ECONOMIC_TOOL_DEFINITIONS


DEFAULT_DATA_FILENAME = "wuhan_hongshan_official.json"
EXPECTED_SCHEMA_VERSION = "spatial-agent.economic-data.v1"
REQUIRED_SOURCE_FIELDS = (
    "name",
    "url",
    "published_at",
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
        self._validation_issues: list[dict[str, str]] = []
        self._load_issue: str | None = None
        self._payload = self._load_payload()
        self._validate_payload()
        self._records = self._normalize_records(self._payload.get("records"))
        raw_provenance = self._payload.get("provenance")
        self._provenance = {
            str(key): str(value)[:512]
            for key, value in (raw_provenance if isinstance(raw_provenance, Mapping) else {}).items()
            if key in {"source", "version", "attribution", "license", "retrieved_at"}
            and value is not None
        }
        self._engine = IndicatorAnalysisEngine(
            self._records,
            dataset_id=self._dataset_id(),
            provenance=self._provenance,
            config=IndicatorAnalysisConfig(
                result_prefix="economic",
                status_codes={
                    "data_unavailable": "economic_data_unavailable",
                    "indicator_unavailable": "economic_indicator_unavailable",
                    "region_unavailable": "economic_region_unavailable",
                    "time_range_unavailable": "economic_time_range_unavailable",
                    "geography_level_unavailable": "economic_geography_level_unavailable",
                    "data_not_found": "economic_data_not_found",
                    "source_evidence_unavailable": "economic_source_evidence_unavailable",
                },
                retryable_codes=("economic_data_unavailable", "economic_source_unverified"),
                max_rows=512,
                max_sources=32,
                include_source_evidence=True,
                include_source_record_count=True,
                include_geography_levels=True,
                include_period_type=True,
                mean_digits=6,
            ),
        )

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
            "source_status": "ready" if status == "ready" else "unavailable",
            "freshness": {
                "retrieved_at": self._provenance.get("retrieved_at"),
                "status": "known" if self._provenance.get("retrieved_at") else "unknown",
            },
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
        return self._engine.list_indicators()

    def _query(self, arguments: Mapping[str, Any]) -> Dict[str, Any]:
        return self._engine.query(arguments)

    def _source_evidence(self, arguments: Mapping[str, Any]) -> Dict[str, Any]:
        return self._engine.source_evidence(arguments)

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
                if source.get("geography_level") not in (None, raw.get("geography_level")):
                    missing.append("source.geography_level_mismatch")
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

    def _validate_payload(self) -> None:
        """Validate the dataset envelope before exposing any observations."""

        raw_records = self._payload.get("records")
        if not isinstance(raw_records, list):
            self._validation_issues.append({"record": "payload", "code": "records_not_array"})
            return
        if not raw_records:
            return
        if self._payload.get("schema_version") != EXPECTED_SCHEMA_VERSION:
            self._validation_issues.append({"record": "payload", "code": "schema_version_mismatch"})
        if self._payload.get("dataset") != "wuhan_hongshan_economic_indicators":
            self._validation_issues.append({"record": "payload", "code": "dataset_mismatch"})
        provenance = self._payload.get("provenance")
        if not isinstance(provenance, Mapping):
            self._validation_issues.append({"record": "payload", "code": "provenance_not_object"})
            return
        missing = [
            name
            for name in ("source", "version", "retrieved_at")
            if provenance.get(name) in (None, "")
        ]
        if missing:
            self._validation_issues.append(
                {"record": "payload", "code": "provenance_incomplete", "fields": ",".join(missing)}
            )

    def _load_payload(self) -> Dict[str, Any]:
        path = self._resolve_path()
        if path is None:
            self._load_issue = "economic_data_unavailable"
            return {"provenance": {"source": "economic-data-not-configured"}, "records": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            self._load_issue = "economic_data_unreadable"
            return {"provenance": {"source": "economic-data-unreadable", "version": str(path)}, "records": []}
        if not isinstance(payload, Mapping):
            self._load_issue = "economic_data_invalid"
            return {"records": []}
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
        if self._load_issue:
            return self._load_issue
        if self._validation_issues:
            return "economic_field_mismatch"
        return "economic_data_unavailable"
