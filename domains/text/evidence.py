"""Text-domain evidence provider used by the generic Runtime."""

from __future__ import annotations

from typing import Any, Mapping


class TextEvidenceProvider:
    domain_id = "text"

    def snapshot(
        self,
        kind: str,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        if kind == "runtime":
            return self.runtime_snapshot(max_files=max_files)
        if kind == "release":
            return self.release_snapshot(
                config_path=config_path,
                max_files=max_files,
            )
        raise ValueError("unknown text evidence kind: " + str(kind))

    def runtime_snapshot(self, *, max_files: int = 10) -> Mapping[str, Any]:
        return {
            "health_status": "ready",
            "data_readiness": "not_applicable",
            "data_evidence": {},
            "data_provenance": {},
        }

    def release_snapshot(
        self,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        return {
            "report_version": 1,
            "domain_id": self.domain_id,
            "status": "not_applicable",
            "data_readiness": "not_applicable",
            "metadata": {"status": "not_applicable"},
            "source_binding": {"status": "not_applicable"},
            "output_manifest": {"status": "not_applicable"},
            "manifest": {"status": "not_applicable"},
        }


TEXT_EVIDENCE_PROVIDER = TextEvidenceProvider()


__all__ = ["TEXT_EVIDENCE_PROVIDER", "TextEvidenceProvider"]
