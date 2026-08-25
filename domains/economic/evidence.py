"""Runtime and release evidence for the Economic Domain Pack."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .catalog import ECONOMIC_DATASET


class EconomicEvidenceProvider:
    def runtime_snapshot(self, *, max_files: int = 10):
        del max_files
        configured = os.environ.get("SPATIAL_AGENT_ECONOMIC_DATA")
        return {
            "health_status": "configured" if configured else "auto_discovery",
            "data_readiness": "external_source_bound",
            "data_evidence": {
                "dataset": ECONOMIC_DATASET,
                "source": "武汉市洪山区人民政府统计信息公开页面",
                "configured_path": str(Path(configured).name) if configured else None,
            },
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
