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

    def snapshot(
        self,
        kind: str,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        """Return one provider-owned projection selected by evidence kind."""
        if kind == "runtime":
            return self.runtime_snapshot(max_files=max_files)
        if kind == "release":
            return self.release_snapshot(
                config_path=config_path,
                max_files=max_files,
            )
        raise ValueError("unknown GIS evidence kind: " + str(kind))

    def runtime_snapshot(self, *, max_files: int = 10) -> Mapping[str, Any]:
        from domains.gis.adapters.runtime_capabilities import runtime_capability_snapshot

        value = runtime_capability_snapshot(max_files=max_files)
        if not isinstance(value, Mapping):
            return {}
        result = dict(value)
        # The legacy snapshot calls this list ``capabilities``.  The generic
        # Runtime evidence seam uses an explicit name so it cannot confuse
        # runtime projections with the static catalog.  Normalize at the
        # Domain adapter instead of making the shared Runtime know GIS names.
        if (
            "capabilities_runtime" not in result
            and isinstance(result.get("capabilities"), list)
        ):
            result["capabilities_runtime"] = list(result["capabilities"])
        return result

    def release_snapshot(
        self,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        from domains.gis.adapters.release_evidence import release_evidence_snapshot

        return release_evidence_snapshot(config_path=config_path, max_files=max_files)


GIS_EVIDENCE_PROVIDER = GisEvidenceProvider()


__all__ = ["GIS_EVIDENCE_PROVIDER", "GisEvidenceProvider"]
