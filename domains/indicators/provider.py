"""Replaceable indicator data Adapter behind the ToolRegistry seam."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Mapping

from agent.data_kinds import build_data_profile
from agent.errors import ToolError

from .catalog import INDICATOR_TOOL_DEFINITIONS


_DEMO_PAYLOAD = {
    "provenance": {
        "source": "local-demo-fixture",
        "version": "0.1",
        "attribution": "仅用于 Runtime 契约演示，不代表真实统计数据",
    },
    "records": [
        {"indicator": "demo_activity_index", "label": "示例活动指数", "region": "区域甲", "period": "2022", "value": 82.0, "unit": "指数"},
        {"indicator": "demo_activity_index", "label": "示例活动指数", "region": "区域甲", "period": "2023", "value": 86.5, "unit": "指数"},
        {"indicator": "demo_activity_index", "label": "示例活动指数", "region": "区域甲", "period": "2024", "value": 91.0, "unit": "指数"},
        {"indicator": "demo_activity_index", "label": "示例活动指数", "region": "区域乙", "period": "2022", "value": 76.0, "unit": "指数"},
        {"indicator": "demo_activity_index", "label": "示例活动指数", "region": "区域乙", "period": "2023", "value": 79.0, "unit": "指数"},
        {"indicator": "demo_activity_index", "label": "示例活动指数", "region": "区域乙", "period": "2024", "value": 81.5, "unit": "指数"},
    ],
}


class IndicatorToolProvider:
    provider_id = "indicator-native"

    def __init__(self, data_path: str | None = None):
        self._data_path = str(data_path or os.environ.get("SPATIAL_AGENT_INDICATOR_DATA") or "")
        self._payload = self._load_payload()
        self._records = [
            dict(item)
            for item in self._payload.get("records", [])
            if isinstance(item, Mapping)
            and item.get("indicator")
            and item.get("region")
            and item.get("period")
            and isinstance(item.get("value"), (int, float))
        ]
        self._provenance = {
            str(key): str(value)[:256]
            for key, value in (self._payload.get("provenance") or {}).items()
            if key in {"source", "version", "attribution", "license"}
            and value is not None
        }

    def definitions(self) -> Mapping[str, Mapping[str, Any]]:
        return deepcopy(INDICATOR_TOOL_DEFINITIONS)

    def health(self) -> Dict[str, Any]:
        ready = bool(self._records)
        return {
            "status": "ready" if ready else "unavailable",
            "data_readiness": "ready" if ready else "not_ready",
            "datasets": [{
                "dataset": "regional_indicators",
                "status": "ready" if ready else "unavailable",
                "record_count": len(self._records),
            }],
            "provenance": dict(self._provenance),
        }

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "list_indicators":
            return self._list_indicators()
        if name == "indicator_query":
            return self._query(arguments)
        raise ToolError("unknown indicator tool", code="unknown_indicator_tool", retryable=False)

    def _list_indicators(self) -> Dict[str, Any]:
        indicators = {}
        for item in self._records:
            entry = indicators.setdefault(
                str(item["indicator"]),
                {"id": str(item["indicator"]), "label": str(item.get("label") or item["indicator"]), "units": set()},
            )
            if item.get("unit"):
                entry["units"].add(str(item["unit"]))
        regions = sorted({str(item["region"]) for item in self._records})
        periods = sorted({str(item["period"]) for item in self._records})
        values = []
        for item in indicators.values():
            values.append({**item, "units": sorted(item["units"])})
        return {
            "indicators": values[:64],
            "regions": regions[:128],
            "periods": periods[:128],
            "provenance": dict(self._provenance),
            "data_profile": build_data_profile(("metrics",)),
        }

    def _query(self, arguments: Mapping[str, Any]) -> Dict[str, Any]:
        if not self._records:
            raise ToolError(
                "indicator data is unavailable",
                category="provider",
                code="indicator_data_unavailable",
                retryable=False,
            )
        indicator = str(arguments.get("indicator") or "").strip()
        regions = [str(item).strip() for item in (arguments.get("regions") or []) if str(item).strip()]
        operation = str(arguments.get("operation") or "latest")
        start = str(arguments.get("period_start") or "")
        end = str(arguments.get("period_end") or "")
        records = [
            dict(item)
            for item in self._records
            if str(item.get("indicator")) == indicator
            and str(item.get("region")) in regions
            and (not start or str(item.get("period")) >= start)
            and (not end or str(item.get("period")) <= end)
        ]
        if not records:
            raise ToolError(
                "indicator data did not match the requested indicator and regions",
                category="provider",
                code="indicator_data_not_found",
                retryable=False,
            )
        records.sort(key=lambda item: (str(item["region"]), str(item["period"])))
        if operation == "latest":
            rows = self._latest_by_region(records)
            profile = build_data_profile(("metrics",))
            result_type = "indicator_metrics_result"
        elif operation == "compare":
            rows = self._latest_by_region(records)
            profile = build_data_profile(("composite", "metrics"))
            result_type = "indicator_comparison_result"
        else:
            rows = records
            profile = build_data_profile(("timeseries", "metrics"))
            result_type = "indicator_timeseries_result"
        numeric = [float(item["value"]) for item in rows]
        metrics = {
            "record_count": len(rows),
            "region_count": len({str(item["region"]) for item in rows}),
            "minimum": min(numeric) if numeric else None,
            "maximum": max(numeric) if numeric else None,
            "mean": mean(numeric) if numeric else None,
        }
        if operation == "trend":
            by_region = {}
            for item in rows:
                by_region.setdefault(str(item["region"]), []).append(item)
            metrics["changes"] = {
                region: round(float(values[-1]["value"]) - float(values[0]["value"]), 6)
                for region, values in by_region.items()
                if len(values) >= 2
            }
        return {
            "result_type": result_type,
            "operation": operation,
            "indicator": indicator,
            "rows": rows[:256],
            "metrics": metrics,
            "data_profile": profile,
            "provenance": dict(self._provenance),
        }

    @staticmethod
    def _latest_by_region(records):
        latest = {}
        for item in records:
            key = str(item["region"])
            if key not in latest or str(item["period"]) > str(latest[key]["period"]):
                latest[key] = item
        return [latest[key] for key in sorted(latest)]

    def _load_payload(self) -> Dict[str, Any]:
        if not self._data_path:
            return deepcopy(_DEMO_PAYLOAD)
        try:
            payload = json.loads(Path(self._data_path).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {"provenance": {"source": "configured-indicator-data"}, "records": []}
        return dict(payload) if isinstance(payload, Mapping) else {"records": []}
