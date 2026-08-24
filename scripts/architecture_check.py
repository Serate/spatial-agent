#!/usr/bin/env python3
"""Run lightweight, dependency-free architecture boundary checks.

This is a static guard for the refactor.  It intentionally reports current
technical-debt metrics without failing merely because the migration is not
complete yet.  Only forbidden top-level domain imports and missing canonical
entrypoints are errors.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
COMPAT_MODULES = {
    "agent/answer_composer.py",
    "agent/capability_routing.py",
    "agent/domain_contract.py",
    "agent/domain_registry.py",
    "agent/planner.py",
    "agent/request_model.py",
    "agent/result_registry.py",
    "agent/rule_planning.py",
    "agent/spatial_intent.py",
    "agent/workflow_templates.py",
}


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _top_level_domain_imports(path: Path) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [{"file": _relative(path), "line": exc.lineno or 0, "error": "syntax_error"}]
    violations = []
    for node in ast.walk(tree):
        if getattr(node, "col_offset", None) != 0:
            continue
        if isinstance(node, ast.ImportFrom):
            imported = node.module
        elif isinstance(node, ast.Import):
            imported = node.names[0].name if node.names else None
        else:
            continue
        if not imported or not imported.startswith("domains."):
            continue
        if _relative(path) in COMPAT_MODULES:
            continue
        violations.append(
            {"file": _relative(path), "line": node.lineno, "module": imported}
        )
    return violations


def build_report() -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    runtime_path = ROOT / "agent" / "runtime.py"
    service_path = ROOT / "agent" / "service.py"
    index_path = ROOT / "web" / "index.html"

    for required in (
        ROOT / "agent" / "runtime.py",
        ROOT / "agent" / "service.py",
        ROOT / "agent" / "runtime_factory.py",
        ROOT / "run_demo.py",
        ROOT / "domains" / "gis",
        ROOT / "domains" / "text",
        ROOT / "domains" / "indicators",
    ):
        if not required.exists():
            errors.append({"path": _relative(required), "code": "missing_entrypoint"})

    if runtime_path.exists() and _line_count(runtime_path) > 1000:
        warnings.append({"path": _relative(runtime_path), "code": "runtime_god_module"})
    if service_path.exists() and _line_count(service_path) > 1000:
        warnings.append({"path": _relative(service_path), "code": "service_god_module"})
    if index_path.exists() and index_path.stat().st_size > 100_000:
        warnings.append({"path": _relative(index_path), "code": "frontend_monolith"})

    for path in sorted((ROOT / "agent").glob("*.py")):
        errors.extend(_top_level_domain_imports(path))

    return {
        "schema_version": "spatial-agent.architecture-check.v1",
        "status": "failed" if errors else "ok",
        "errors": errors[:32],
        "warnings": warnings[:32],
        "metrics": {
            "agent_python_files": len(list((ROOT / "agent").glob("*.py"))),
            "runtime_lines": _line_count(runtime_path) if runtime_path.exists() else 0,
            "service_lines": _line_count(service_path) if service_path.exists() else 0,
            "frontend_index_bytes": index_path.stat().st_size if index_path.exists() else 0,
            "compat_modules": sorted(COMPAT_MODULES),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="fail on reported errors")
    args = parser.parse_args()
    report = build_report()
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 1 if args.strict and report["status"] != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
