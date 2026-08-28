"""Generate a compact source/file/function index without copying source text."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "spatial-agent.code-index.v1"
OVERRIDES_SCHEMA_VERSION = "spatial-agent.code-index-overrides.v1"
DEFAULT_ROOTS = ("agent", "domains", "scripts", "web/src")
SOURCE_SUFFIXES = {".py": "python", ".js": "javascript"}


def build_index(repo_root: Path, overrides_path: Path, roots: tuple[str, ...]) -> dict[str, Any]:
    overrides = _load_json(overrides_path)
    if overrides.get("schema_version") != OVERRIDES_SCHEMA_VERSION:
        raise ValueError("unsupported code-index-overrides schema")
    override_files = overrides.get("files")
    if not isinstance(override_files, dict):
        raise ValueError("code-index-overrides files must be an object")
    defaults = overrides.get("defaults") if isinstance(overrides.get("defaults"), dict) else {}
    files: list[dict[str, Any]] = []
    discovered: set[str] = set()
    for root_name in roots:
        root = repo_root / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            language = SOURCE_SUFFIXES.get(path.suffix.lower())
            if language is None or not path.is_file() or any(part == "__pycache__" for part in path.parts):
                continue
            relative = path.relative_to(repo_root).as_posix()
            discovered.add(relative)
            files.append(_index_file(path, relative, language, defaults, override_files.get(relative, {})))
    unknown_overrides = sorted(set(override_files) - discovered)
    if unknown_overrides:
        raise ValueError("override points to undiscovered file: " + ", ".join(unknown_overrides))
    return {
        "schema_version": SCHEMA_VERSION,
        "roots": list(roots),
        "file_count": len(files),
        "files": files,
    }


def _index_file(
    path: Path,
    relative: str,
    language: str,
    defaults: dict[str, Any],
    override: Any,
) -> dict[str, Any]:
    if not isinstance(override, dict):
        raise ValueError("override must be an object: " + relative)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("cannot read " + relative) from exc
    if language == "python":
        try:
            tree = ast.parse(source, filename=relative)
        except SyntaxError as exc:
            raise ValueError("cannot parse " + relative) from exc
        symbols = _public_symbols(tree)
        imports = sorted(_project_imports(tree))
    else:
        symbols = _javascript_symbols(source)
        imports = sorted(_javascript_imports(source))
    line_count = len(source.splitlines())
    entry: dict[str, Any] = {
        "path": relative,
        "language": language,
        "line_count": line_count,
        "layer": str(override.get("layer", defaults.get("layer", "unclassified"))),
        "role": str(override.get("role", defaults.get("role", "未分类源码"))),
        "stage": override.get("stage", defaults.get("stage")),
        "stability": str(override.get("stability", defaults.get("stability", "internal"))),
        "public_symbols": symbols,
        "imports": imports,
    }
    for field in ("depends_on", "used_by", "tests"):
        value = override.get(field)
        if isinstance(value, list):
            entry[field] = [str(item).replace("\\", "/") for item in value[:32]]
    return entry


def _public_symbols(tree: ast.Module) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            symbols.append({"name": node.name, "kind": "function", "line": node.lineno})
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            symbols.append({"name": node.name, "kind": "class", "line": node.lineno})
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not child.name.startswith("_"):
                    symbols.append({"name": node.name + "." + child.name, "kind": "method", "line": child.lineno})
    return symbols


def _project_imports(tree: ast.Module) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            if name.startswith(("agent", "domains")):
                imports.add(name)
    return imports


def _javascript_symbols(source: str) -> list[dict[str, Any]]:
    patterns = (
        re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"),
        re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)"),
        re.compile(r"^\s*export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="),
    )
    symbols: list[dict[str, Any]] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        for pattern in patterns:
            match = pattern.match(line)
            if match and not match.group(1).startswith("_"):
                kind = "function" if "function" in pattern.pattern else "class" if "class" in pattern.pattern else "export"
                symbols.append({"name": match.group(1), "kind": kind, "line": line_number})
                break
    return symbols


def _javascript_imports(source: str) -> set[str]:
    imports: set[str] = set()
    pattern = re.compile(r"(?:from|import)\s*[('\"]([^'\")]+)")
    for match in pattern.finditer(source):
        value = match.group(1)
        if value.startswith((".", "/")):
            imports.add(value[:160])
    return imports


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON: " + path.as_posix()) from exc
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object: " + path.as_posix())
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--overrides", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--roots", nargs="+", default=list(DEFAULT_ROOTS))
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    overrides = (args.overrides or repo_root / "docs/code-index-overrides.json").resolve()
    output = (args.output or repo_root / "docs/code-index.json").resolve()
    index = build_index(repo_root, overrides, tuple(str(root) for root in args.roots))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": output.relative_to(repo_root).as_posix(), "file_count": index["file_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
