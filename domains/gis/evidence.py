"""GIS-owned evidence provider.

The generic Runtime consumes this Module through ``DomainPack``. The legacy
health, analysis-ready and release implementations remain behind this Adapter
for backwards compatibility with old scripts and artifacts, but no public
generic entry point imports GIS data policy directly.
"""

from __future__ import annotations

from typing import Any, Mapping


class GisEvidenceProvider:
    """Adapt the existing GIS evidence implementations to Domain Pack seams."""

    domain_id = "gis"

    def runtime_snapshot(self, *, max_files: int = 10) -> Mapping[str, Any]:
        from agent.runtime_capabilities import runtime_capability_snapshot

        return runtime_capability_snapshot(max_files=max_files)

    def release_snapshot(
        self,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        from agent.release_evidence import release_evidence_snapshot

        return release_evidence_snapshot(config_path=config_path, max_files=max_files)


GIS_EVIDENCE_PROVIDER = GisEvidenceProvider()


__all__ = ["GIS_EVIDENCE_PROVIDER", "GisEvidenceProvider"]
