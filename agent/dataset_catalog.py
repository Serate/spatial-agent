import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


@dataclass(frozen=True)
class DatasetEntry:
    name: str
    kind: str
    format: str
    role: str
    files: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "format": self.format,
            "role": self.role,
            "files": list(self.files),
            "file_count": len(self.files),
        }


class DatasetCatalog:
    """Reads local dataset configuration without binding the Agent to file formats."""

    def __init__(self, root: str, entries: Mapping[str, DatasetEntry]):
        self.root = str(Path(root))
        self._entries = dict(entries)

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
            )
        return cls(root, entries)

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
        return {
            "root": self.root,
            "datasets": [entry.to_dict() for entry in self.list_entries()],
        }


def _resolve_files(root: str, definition: Mapping[str, Any]) -> List[str]:
    base = Path(root)
    if "path" in definition:
        path = base / definition["path"]
        return [str(path)] if path.exists() else []
    if "glob" in definition:
        pattern = str(base / definition["glob"])
        return sorted(glob.glob(pattern, recursive=True))
    return []
