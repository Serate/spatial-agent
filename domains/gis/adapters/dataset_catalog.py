import glob
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


PROVENANCE_FIELDS = ("source", "version", "attribution", "license")
DISCOVERY_FIELDS = (
    "stage",
    "status",
    "coverage",
    "time_range",
    "crs",
    "resolution",
    "source_url",
    "availability_reason",
)
_MAX_PROVENANCE_VALUE_LENGTH = 256
_MAX_DISCOVERY_VALUE_LENGTH = 256


def controlled_discovery(metadata: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return bounded catalog metadata used for data discovery.

    Discovery metadata is descriptive evidence, not a permission to execute a
    tool.  In particular, ``status`` lets a planner distinguish a readable
    analysis input from a downloaded archive that still needs extraction or
    clipping.  Values are deliberately bounded so catalog summaries remain
    safe to put into planner context and runtime evidence.
    """
    if not isinstance(metadata, Mapping):
        return {}
    result: Dict[str, Any] = {}
    for field in DISCOVERY_FIELDS:
        value = metadata.get(field)
        if value is None or isinstance(value, (dict, list, tuple, set)):
            continue
        text = str(value).strip()
        text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
        text = " ".join(text.split())
        if text:
            result[field] = text[:_MAX_DISCOVERY_VALUE_LENGTH]
    tags = metadata.get("tags")
    if isinstance(tags, (list, tuple, set)):
        clean_tags = []
        for tag in tags:
            if isinstance(tag, (dict, list, tuple, set)):
                continue
            text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(tag)).strip()
            text = " ".join(text.split())
            if text and text not in clean_tags:
                clean_tags.append(text[:64])
        if clean_tags:
            result["tags"] = clean_tags[:32]
    return result


def controlled_provenance(metadata: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """Return only bounded, explicitly supported dataset provenance fields."""
    if not isinstance(metadata, Mapping):
        return {}
    result: Dict[str, str] = {}
    for field in PROVENANCE_FIELDS:
        value = metadata.get(field)
        if value is None or isinstance(value, (dict, list, tuple, set)):
            continue
        text = str(value).strip()
        if not text:
            continue
        text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
        text = " ".join(text.split())
        if text:
            result[field] = text[:_MAX_PROVENANCE_VALUE_LENGTH]
    return result


@dataclass(frozen=True)
class DatasetEntry:
    name: str
    kind: str
    format: str
    role: str
    files: List[str]
    source: Optional[str] = None
    version: Optional[str] = None
    attribution: Optional[str] = None
    license: Optional[str] = None
    stage: Optional[str] = None
    status: Optional[str] = None
    coverage: Optional[str] = None
    time_range: Optional[str] = None
    crs: Optional[str] = None
    resolution: Optional[str] = None
    tags: Sequence[str] = ()
    source_url: Optional[str] = None
    availability_reason: Optional[str] = None

    @property
    def provenance(self) -> Dict[str, str]:
        return controlled_provenance(
            {
                "source": self.source,
                "version": self.version,
                "attribution": self.attribution,
                "license": self.license,
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "kind": self.kind,
            "format": self.format,
            "role": self.role,
            "files": list(self.files),
            "file_count": len(self.files),
        }
        result.update(self.provenance)
        result.update(self.discovery)
        return result

    @property
    def discovery(self) -> Dict[str, Any]:
        return controlled_discovery(
            {
                "stage": self.stage,
                "status": self.status,
                "coverage": self.coverage,
                "time_range": self.time_range,
                "crs": self.crs,
                "resolution": self.resolution,
                "tags": self.tags,
                "source_url": self.source_url,
                "availability_reason": self.availability_reason,
            }
        )


class DatasetCatalog:
    """Reads local dataset configuration without binding the Agent to file formats."""

    def __init__(
        self,
        root: str,
        entries: Mapping[str, DatasetEntry],
        manifest_path: Optional[str] = None,
        manifest_required: bool = False,
        analysis_ready_report_path: Optional[str] = None,
        analysis_ready_required: bool = False,
    ):
        self.root = str(Path(root))
        self._entries = dict(entries)
        self.manifest_path = str(manifest_path) if manifest_path else None
        self.manifest_required = bool(manifest_required)
        self.analysis_ready_report_path = (
            str(analysis_ready_report_path)
            if analysis_ready_report_path
            else None
        )
        self.analysis_ready_required = bool(analysis_ready_required)

    @classmethod
    def from_json(cls, path: str) -> "DatasetCatalog":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        root = payload["root"]
        entries = {}
        for name, definition in payload.get("datasets", {}).items():
            files = _resolve_files(root, definition)
            entries[name] = DatasetEntry(
                name=name,
                kind=definition["kind"],
                format=definition["format"],
                role=definition.get("role", ""),
                files=files,
                source=definition.get("source"),
                version=definition.get("version"),
                attribution=definition.get("attribution"),
                license=definition.get("license"),
                stage=definition.get("stage"),
                # Existing configs predate discovery metadata.  Keep the
                # field absent so old manifests remain byte-compatible;
                # discovery treats an absent status as legacy-ready while
                # explicit partial/pending entries remain gated.
                status=definition.get("status"),
                coverage=definition.get("coverage"),
                time_range=definition.get("time_range"),
                crs=definition.get("crs"),
                resolution=definition.get("resolution"),
                tags=definition.get("tags", ()),
                source_url=definition.get("source_url"),
                availability_reason=definition.get("availability_reason"),
            )
        manifest_value = payload.get("manifest")
        manifest_required = bool(payload.get("manifest_required", False))
        if isinstance(manifest_value, Mapping):
            manifest_path = manifest_value.get("path")
            manifest_required = bool(
                manifest_value.get("required", manifest_required)
            )
        else:
            manifest_path = manifest_value
        if isinstance(manifest_path, str) and manifest_path.strip():
            manifest_candidate = Path(manifest_path)
            if not manifest_candidate.is_absolute():
                manifest_candidate = Path(path).parent / manifest_candidate
            manifest_path = str(manifest_candidate)
        else:
            manifest_path = None
        analysis_value = payload.get("analysis_ready")
        analysis_required = False
        if isinstance(analysis_value, Mapping):
            analysis_path = analysis_value.get("report") or analysis_value.get("path")
            analysis_required = bool(analysis_value.get("required", False))
        else:
            analysis_path = analysis_value
        analysis_required = bool(
            payload.get("analysis_ready_required", analysis_required)
        )
        if isinstance(analysis_path, str) and analysis_path.strip():
            analysis_candidate = Path(analysis_path)
            if not analysis_candidate.is_absolute():
                analysis_candidate = Path(path).parent / analysis_candidate
            analysis_path = str(analysis_candidate)
        else:
            analysis_path = None
        return cls(
            root,
            entries,
            manifest_path=manifest_path,
            manifest_required=manifest_required,
            analysis_ready_report_path=analysis_path,
            analysis_ready_required=analysis_required,
        )

    def get(self, name: str) -> Optional[DatasetEntry]:
        return self._entries.get(name)

    def require(self, name: str) -> DatasetEntry:
        entry = self.get(name)
        if entry is None:
            raise KeyError("unknown dataset: " + name)
        return entry

    def list_entries(self) -> List[DatasetEntry]:
        return list(self._entries.values())

    def discover(
        self,
        *,
        kind: Optional[str] = None,
        required_tags: Iterable[str] = (),
        stage: Optional[str] = None,
        status: Optional[str] = "ready",
    ) -> List[DatasetEntry]:
        """Find data candidates using catalog facts, not file-name rules.

        The default only returns ``ready`` entries so callers do not
        accidentally select archives, partial downloads, or data awaiting
        CRS/AOI preparation.  Passing ``status=None`` intentionally includes
        all registered candidates for inspection and clarification.
        """
        wanted_tags = {str(tag).strip() for tag in required_tags if str(tag).strip()}
        matches = []
        for entry in self.list_entries():
            if kind and entry.kind != kind:
                continue
            if stage and entry.stage != stage:
                continue
            if status == "ready":
                if entry.status not in (None, "ready"):
                    continue
            elif status is not None and entry.status != status:
                continue
            if wanted_tags and not wanted_tags.issubset(set(entry.tags)):
                continue
            matches.append(entry)
        return sorted(matches, key=lambda item: item.name)

    def discovery_summary(self) -> Dict[str, Any]:
        """Return bounded counts for planner context and readiness evidence."""
        entries = self.list_entries()
        by_status: Dict[str, int] = {}
        by_kind: Dict[str, int] = {}
        for entry in entries:
            effective_status = entry.status or "ready"
            by_status[effective_status] = by_status.get(effective_status, 0) + 1
            by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1
        return {
            "dataset_count": len(entries),
            "ready_count": len(self.discover(status="ready")),
            "by_status": dict(sorted(by_status.items())),
            "by_kind": dict(sorted(by_kind.items())),
        }

    def summary(self) -> Dict[str, Any]:
        result = {
            "root": self.root,
            "datasets": [entry.to_dict() for entry in self.list_entries()],
            "discovery": self.discovery_summary(),
        }
        if self.manifest_path:
            result["manifest_configured"] = True
            result["manifest_required"] = self.manifest_required
        if self.analysis_ready_report_path:
            result["analysis_ready_configured"] = True
            result["analysis_ready_required"] = self.analysis_ready_required
        return result


def _resolve_files(root: str, definition: Mapping[str, Any]) -> List[str]:
    base = Path(root)
    if "path" in definition:
        path = base / definition["path"]
        return [str(path)] if path.exists() else []
    if "glob" in definition:
        pattern = str(base / definition["glob"])
        return sorted(glob.glob(pattern, recursive=True))
    return []
