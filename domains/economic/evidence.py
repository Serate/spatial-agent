"""Runtime and release evidence for the Economic Domain Pack."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .catalog import ECONOMIC_DATASET


class EconomicEvidenceProvider:
    def runtime_snapshot(self, *, max_files: int = 10):
        del max_files
        from .provider import EconomicToolProvider

        configured = os.environ.get("SPATIAL_AGENT_ECONOMIC_DATA")
        health = EconomicToolProvider(data_path=configured or None).health()
        provenance = health.get("provenance") if isinstance(health.get("provenance"), dict) else {}
        status = str(health.get("status") or "unavailable")
        return {
            "health_status": status,
            "data_readiness": str(health.get("data_readiness") or status),
            "source_status": str(health.get("source_status") or "unavailable"),
            "data_evidence": {
                "dataset": str(health.get("dataset") or ECONOMIC_DATASET)[:96],
                "source": str(provenance.get("source") or "未知来源")[:256],
                "configured_path": str(Path(configured).name) if configured else None,
                "record_count": int(health.get("record_count") or 0),
                "validation_issue_count": int(health.get("validation_issue_count") or 0),
                "reason_code": health.get("reason_code"),
            },
            "data_provenance": dict(provenance),
            "freshness": dict(health.get("freshness") or {}),
            "capabilities": [
                "economic_indicator_discovery",
                "economic_indicator_latest",
                "economic_indicator_trend",
                "economic_indicator_compare",
                "economic_source_evidence",
            ],
        }

    def release_snapshot(self, *, config_path: str | None = None, max_files: int = 10):
        del max_files
        return {
            "status": "source_bound",
            "verification_mode": "official-page-normalized-json",
            "domain_id": "economic",
            "dataset": ECONOMIC_DATASET,
            "config_path": str(config_path)[:256] if config_path else None,
            "source_policy": "每条观测必须保留 URL、发布日期、检索日期和字段/表格定位",
        }


ECONOMIC_EVIDENCE_PROVIDER = EconomicEvidenceProvider()
