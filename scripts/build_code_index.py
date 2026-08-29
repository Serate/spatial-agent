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
SEMANTIC_FIELDS = ("layer", "role", "stage", "stability")
DEFAULT_SEMANTICS = {
    "layer": "unclassified",
    "role": "未分类源码",
    "stage": None,
    "stability": "internal",
}


def build_index(repo_root: Path, overrides_path: Path, roots: tuple[str, ...]) -> dict[str, Any]:
    overrides = _load_json(overrides_path)
    if overrides.get("schema_version") != OVERRIDES_SCHEMA_VERSION:
        raise ValueError("unsupported code-index-overrides schema")
    override_files = overrides.get("files")
    if not isinstance(override_files, dict):
        raise ValueError("code-index-overrides files must be an object")
    defaults = overrides.get("defaults") if isinstance(overrides.get("defaults"), dict) else {}
    rules = _semantic_rules(overrides.get("rules"))
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
            files.append(
                _index_file(
                    path,
                    relative,
                    language,
                    defaults,
                    rules,
                    override_files.get(relative, {}),
                )
            )
    unknown_overrides = sorted(set(override_files) - discovered)
    if unknown_overrides:
        raise ValueError("override points to undiscovered file: " + ", ".join(unknown_overrides))
    agent_entries = [entry for entry in files if entry["path"].startswith("agent/")]
    semantic_counts = {
        "classified_files": sum(
            1 for entry in files if entry["semantic_source"] != "default"
        ),
        "file_override_files": sum(
            1 for entry in files if entry["semantic_source"] == "file-override"
        ),
        "path_rule_files": sum(
            1 for entry in files if entry["semantic_source"] == "path-rule"
        ),
        "default_files": sum(1 for entry in files if entry["semantic_source"] == "default"),
        "agent_files": len(agent_entries),
        "agent_files_with_responsibility": sum(
            1 for entry in agent_entries if entry.get("responsibility")
        ),
        "agent_files_with_module_doc": sum(
            1 for entry in agent_entries if entry.get("responsibility_source") == "module-doc"
        ),
    }
    semantic_counts["coverage_percent"] = round(
        100 * semantic_counts["classified_files"] / len(files), 2
    ) if files else 100.0
    return {
        "schema_version": SCHEMA_VERSION,
        "roots": list(roots),
        "file_count": len(files),
        "semantic_index": semantic_counts,
        "files": files,
    }


def _index_file(
    path: Path,
    relative: str,
    language: str,
    defaults: dict[str, Any],
    rules: list[dict[str, Any]],
    override: Any,
) -> dict[str, Any]:
    if not isinstance(override, dict):
        raise ValueError("override must be an object: " + relative)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("cannot read " + relative) from exc
    module_tree: ast.Module | None = None
    if language == "python":
        try:
            tree = ast.parse(source, filename=relative)
        except SyntaxError as exc:
            raise ValueError("cannot parse " + relative) from exc
        module_tree = tree
        symbols = _public_symbols(tree)
        imports = sorted(_project_imports(tree))
    else:
        symbols = _javascript_symbols(source)
        imports = sorted(_javascript_imports(source))
    line_count = len(source.splitlines())
    semantic, semantic_source, semantic_level = _resolve_semantics(
        relative, defaults, rules, override
    )
    responsibility = _module_summary(source, module_tree, language)
    responsibility_source = "module-doc" if responsibility else "semantic-role"
    if not responsibility:
        responsibility = str(semantic["role"])
    entry: dict[str, Any] = {
        "path": relative,
        "language": language,
        "line_count": line_count,
        "layer": str(semantic["layer"]),
        "role": str(semantic["role"]),
        "stage": semantic["stage"],
        "stability": str(semantic["stability"]),
        "semantic_source": semantic_source,
        "semantic_level": semantic_level,
        "responsibility": responsibility,
        "responsibility_source": responsibility_source,
        "public_symbols": symbols,
        "imports": imports,
    }
    for field in ("depends_on", "used_by", "tests"):
        value = override.get(field)
        if isinstance(value, list):
            entry[field] = [str(item).replace("\\", "/") for item in value[:32]]
    return entry


def _module_summary(
    source: str, tree: ast.Module | None, language: str
) -> str:
    """Extract a short module responsibility without indexing source content."""
    if language == "python" and tree is not None:
        text = ast.get_docstring(tree, clean=True) or ""
    elif language == "javascript":
        comments = []
        for line in source.splitlines()[:12]:
            stripped = line.strip()
            if stripped.startswith(("//", "/*", "*", "*/")):
                comments.append(stripped.lstrip("/* ").rstrip("*/ "))
            elif comments:
                break
        text = " ".join(comments)
    else:
        text = ""
    first_paragraph = next((part.strip() for part in text.split("\n\n") if part.strip()), "")
    first_paragraph = " ".join(first_paragraph.split())
    return first_paragraph[:240]


def _semantic_rules(value: Any) -> list[dict[str, Any]]:
    """Validate and normalize path rules from the human-maintained manifest."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("code-index-overrides rules must be an array")
    rules: list[dict[str, Any]] = []
    for index, raw_rule in enumerate(value):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"semantic rule {index} must be an object")
        prefix = str(raw_rule.get("prefix") or "").replace("\\", "/").strip()
        if not prefix:
            raise ValueError(f"semantic rule {index} has no prefix")
        rule = {"prefix": prefix}
        for field in SEMANTIC_FIELDS:
            if field in raw_rule:
                rule[field] = raw_rule[field]
        if not any(field in rule for field in SEMANTIC_FIELDS):
            raise ValueError(f"semantic rule {index} has no semantic fields")
        rules.append(rule)
    return rules


def _resolve_semantics(
    relative: str,
    defaults: dict[str, Any],
    rules: list[dict[str, Any]],
    override: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    """Resolve exact file metadata over the most-specific path rule and defaults."""
    semantic = dict(DEFAULT_SEMANTICS)
    semantic.update({field: defaults[field] for field in SEMANTIC_FIELDS if field in defaults})
    matching_rules = [rule for rule in rules if relative.startswith(str(rule["prefix"]))]
    rule = max(matching_rules, key=lambda item: len(str(item["prefix"])), default=None)
    if rule is not None:
        semantic.update({field: rule[field] for field in SEMANTIC_FIELDS if field in rule})
    exact_fields = [field for field in SEMANTIC_FIELDS if field in override]
    semantic.update({field: override[field] for field in exact_fields})
    if exact_fields:
        return semantic, "file-override", "file"
    if rule is not None:
        return semantic, "path-rule", "package"
    return semantic, "default", "unclassified"


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
