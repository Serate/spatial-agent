"""Replaceable indicator data Adapter behind the ToolRegistry seam."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping

from agent.analysis.indicator_core import IndicatorAnalysisConfig, IndicatorAnalysisEngine
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
        self._engine = IndicatorAnalysisEngine(
            self._records,
            dataset_id="regional_indicators",
            provenance=self._provenance,
            config=IndicatorAnalysisConfig(
                result_prefix="indicator",
                status_codes={
                    "data_unavailable": "indicator_data_unavailable",
                    "indicator_unavailable": "indicator_data_not_found",
                    "region_unavailable": "indicator_data_not_found",
                    "time_range_unavailable": "indicator_data_not_found",
                    "data_not_found": "indicator_data_not_found",
                    "source_evidence_unavailable": "indicator_data_not_found",
                },
                max_rows=256,
            ),
        )

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
        return self._engine.list_indicators()

    def _query(self, arguments: Mapping[str, Any]) -> Dict[str, Any]:
        result = self._engine.query(arguments)
        if result.get("status") != "ready":
            raise ToolError(
                "indicator data did not match the requested indicator and regions",
                category="provider",
                code=str(result.get("code") or "indicator_data_not_found"),
                retryable=bool(result.get("retryable")),
            )
        return result

    def _load_payload(self) -> Dict[str, Any]:
        if not self._data_path:
            return deepcopy(_DEMO_PAYLOAD)
        try:
            payload = json.loads(Path(self._data_path).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {"provenance": {"source": "configured-indicator-data"}, "records": []}
        return dict(payload) if isinstance(payload, Mapping) else {"records": []}
