import glob
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


PROVENANCE_FIELDS = ("source", "version", "attribution", "license")
_MAX_PROVENANCE_VALUE_LENGTH = 256


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
        return result


class DatasetCatalog:
    """Reads local dataset configuration without binding the Agent to file formats."""

    def __init__(
        self,
        root: str,
        entries: Mapping[str, DatasetEntry],
        manifest_path: Optional[str] = None,
        manifest_required: bool = False,
    ):
        self.root = str(Path(root))
        self._entries = dict(entries)
        self.manifest_path = str(manifest_path) if manifest_path else None
        self.manifest_required = bool(manifest_required)

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
        return cls(
            root,
            entries,
            manifest_path=manifest_path,
            manifest_required=manifest_required,
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

    def summary(self) -> Dict[str, Any]:
        result = {
            "root": self.root,
            "datasets": [entry.to_dict() for entry in self.list_entries()],
        }
        if self.manifest_path:
            result["manifest_configured"] = True
            result["manifest_required"] = self.manifest_required
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
