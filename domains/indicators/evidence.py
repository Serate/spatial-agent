"""Bounded evidence Adapter for the indicator Domain Pack."""

from __future__ import annotations


class IndicatorEvidenceProvider:
    def runtime_snapshot(self, *, max_files: int = 10):
        del max_files
        return {
            "health_status": "ready",
            "data_readiness": "ready",
            "data_evidence": {
                "dataset": "regional_indicators",
                "source": "indicator-provider",
            },
            "capabilities": ["indicator_discovery", "indicator_latest", "indicator_trend", "indicator_compare"],
        }

    def release_snapshot(self, *, config_path=None, max_files: int = 10):
        del config_path, max_files
        return {
            "status": "not_configured",
            "verification_mode": "runtime_fixture_or_configured_file",
            "domain_id": "indicators",
        }


INDICATOR_EVIDENCE_PROVIDER = IndicatorEvidenceProvider()
