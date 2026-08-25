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
# Simple historical re-exports.  These modules are deliberately allowed to
# keep their one-way Domain import while old callers migrate.
COMPAT_SHIMS = {
    "agent/answer_composer.py",
    "agent/data_quality.py",
    "agent/dataset_catalog.py",
    "agent/dataset_manifest.py",
    "agent/dataset_probe.py",
    "agent/geometry_export.py",
    "agent/raster_alignment.py",
    "agent/raster_backend.py",
    "agent/spatial_backend.py",
}

# Legacy facades with a small amount of compatibility adaptation.  They are
# not public domain-neutral engines, but are also not simple re-exports.
COMPAT_FACADES = {
    "agent/capability_routing.py",
    "agent/planner.py",
    "agent/rule_planning.py",
    "agent/spatial_intent.py",
}

# Real public contracts/engines must never be hidden by a compatibility
# exemption.  Keep this set explicit so the guard reports a classification
# error if a future edit puts one back into a compat list.
PUBLIC_MODULES = {
    "agent/domain_catalog.py",
    "agent/domain_contract.py",
    "agent/domain_registry.py",
    "agent/request_model.py",
    "agent/result_registry.py",
    "agent/workflow_templates.py",
}

COMPAT_MODULES = COMPAT_SHIMS | COMPAT_FACADES


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
    index_path = ROOT / "web" / "src" / "index.html"

    overlap = sorted(PUBLIC_MODULES & COMPAT_MODULES)
    if overlap:
        errors.append(
            {
                "code": "public_module_marked_compat",
                "modules": overlap,
            }
        )
    for compat_kind, modules in (
        ("shim", COMPAT_SHIMS),
        ("facade", COMPAT_FACADES),
    ):
        for module in sorted(modules):
            if not (ROOT / module).exists():
                errors.append(
                    {
                        "code": "compat_module_missing",
                        "kind": compat_kind,
                        "file": module,
                    }
                )

    for required in (
        ROOT / "agent" / "runtime.py",
        ROOT / "agent" / "service.py",
        ROOT / "agent" / "runtime_factory.py",
        ROOT / "agent" / "runtime_core" / "projection.py",
        ROOT / "agent" / "runtime_core" / "planning.py",
        ROOT / "agent" / "runtime_core" / "execution.py",
        ROOT / "agent" / "runtime_core" / "control.py",
        ROOT / "agent" / "runtime_core" / "planning_surface.py",
        ROOT / "agent" / "runtime_core" / "run_lifecycle.py",
        ROOT / "agent" / "runtime_core" / "decision_resume.py",
        ROOT / "agent" / "runtime_core" / "recovery.py",
        ROOT / "agent" / "runtime_core" / "preview.py",
        ROOT / "agent" / "runtime_core" / "plan_evidence.py",
        ROOT / "agent" / "runtime_core" / "capabilities.py",
        ROOT / "agent" / "runtime_state.py",
        ROOT / "agent" / "application" / "run.py",
        ROOT / "agent" / "application" / "actions.py",
        ROOT / "agent" / "application" / "decisions.py",
        ROOT / "agent" / "application" / "interactions.py",
        ROOT / "agent" / "application" / "sessions.py",
        ROOT / "agent" / "application" / "catalog.py",
        ROOT / "agent" / "application" / "run_recovery.py",
        ROOT / "agent" / "application" / "comparisons.py",
        ROOT / "agent" / "application" / "inspection.py",
        ROOT / "agent" / "application" / "submission.py",
        ROOT / "agent" / "web_assets.py",
        ROOT / "run_demo.py",
        ROOT / "domains" / "gis",
        ROOT / "domains" / "text",
        ROOT / "domains" / "indicators",
        ROOT / "web" / "src" / "index.html",
        ROOT / "web" / "src" / "styles.css",
        ROOT / "web" / "src" / "console_app.js",
        ROOT / "scripts" / "build_console.py",
    ):
        if not required.exists():
            errors.append({"path": _relative(required), "code": "missing_entrypoint"})

    if runtime_path.exists() and _line_count(runtime_path) > 1000:
        warnings.append({"path": _relative(runtime_path), "code": "runtime_god_module"})
    if runtime_path.exists():
        source = runtime_path.read_text(encoding="utf-8")
        if "from .runtime_core import projection" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_projection_seam_missing",
                }
            )
        if "from .runtime_core import planning" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_planning_seam_missing",
                }
            )
        if "from .runtime_core import execution" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_execution_seam_missing",
                }
            )
        if "from .runtime_core.control import RunControl" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_control_seam_missing",
                }
            )
        if "from .runtime_core.capabilities import RuntimeCapabilitySurface" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_capability_surface_missing",
                }
            )
        if "from .runtime_state import" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_state_seam_missing",
                }
            )
        if "from .runtime_core.planning_surface import RuntimePlanningSurface" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_planning_surface_missing",
                }
            )
        if "from .runtime_core.run_lifecycle import RuntimeRunLifecycle" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_run_lifecycle_missing",
                }
            )
        if "from .runtime_core.decision_resume import RuntimeDecisionResume" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_decision_resume_missing",
                }
            )
        if "from .runtime_core.recovery import RuntimeRecoverySurface" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_recovery_surface_missing",
                }
            )
        if "from .runtime_core.preview import RuntimePreviewSurface" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_preview_surface_missing",
                }
            )
        if "from .runtime_core.plan_evidence import" not in source:
            errors.append(
                {
                    "file": _relative(runtime_path),
                    "code": "runtime_plan_evidence_surface_missing",
                }
            )
    if service_path.exists() and _line_count(service_path) > 1000:
        warnings.append({"path": _relative(service_path), "code": "service_god_module"})
    if service_path.exists():
        source = service_path.read_text(encoding="utf-8")
        if "from agent.application.run import RunApplication" not in source:
            errors.append(
                {
                    "file": _relative(service_path),
                    "code": "service_run_application_seam_missing",
                }
            )
        if "from agent.application.sessions import SessionApplication" not in source:
            errors.append(
                {
                    "file": _relative(service_path),
                    "code": "service_session_application_seam_missing",
                }
            )
        if "from agent.application.actions import ActionApplication" not in source:
            errors.append(
                {
                    "file": _relative(service_path),
                    "code": "service_action_application_seam_missing",
                }
            )
        if "from agent.application.decisions import DecisionApplication" not in source:
            errors.append(
                {
                    "file": _relative(service_path),
                    "code": "service_decision_application_seam_missing",
                }
            )
        if "from agent.application.interactions import InteractionApplication" not in source:
            errors.append(
                {
                    "file": _relative(service_path),
                    "code": "service_interaction_application_seam_missing",
                }
            )
        if "agent.application.catalog" not in source or "CatalogApplication" not in source:
            errors.append(
                {
                    "file": _relative(service_path),
                    "code": "service_catalog_application_seam_missing",
                }
            )
        if "from agent.application.run_recovery import RunRecoveryApplication" not in source:
            errors.append(
                {
                    "file": _relative(service_path),
                    "code": "service_run_recovery_application_seam_missing",
                }
            )
        if "from agent.application.comparisons import ComparisonApplication" not in source:
            errors.append(
                {
                    "file": _relative(service_path),
                    "code": "service_comparison_application_seam_missing",
                }
            )
        if "from agent.application.inspection import InspectionApplication" not in source:
            errors.append(
                {
                    "file": _relative(service_path),
                    "code": "service_inspection_application_seam_missing",
                }
            )
        if "from agent.application.submission import SubmissionApplication" not in source:
            errors.append(
                {
                    "file": _relative(service_path),
                    "code": "service_submission_application_seam_missing",
                }
            )
    if index_path.exists() and index_path.stat().st_size > 100_000:
        warnings.append({"path": _relative(index_path), "code": "frontend_monolith"})
    if index_path.exists():
        source = index_path.read_text(encoding="utf-8")
        for marker in ('href="./styles.css"', 'src="./console_app.js"'):
            if marker not in source:
                errors.append(
                    {
                        "file": _relative(index_path),
                        "code": "frontend_source_asset_seam_missing",
                        "marker": marker,
                    }
                )

    for path in sorted((ROOT / "agent").glob("*.py")):
        errors.extend(_top_level_domain_imports(path))

    gis_domain = ROOT / "domains" / "gis" / "domain.py"
    if gis_domain.exists():
        source = gis_domain.read_text(encoding="utf-8")
        if "from .adapters.spatial import" not in source:
            errors.append({"file": _relative(gis_domain), "code": "gis_adapter_seam_missing"})
        for forbidden in ("from agent.spatial_backend import", "from agent.dataset_catalog import"):
            if forbidden in source:
                errors.append(
                    {
                        "file": _relative(gis_domain),
                        "code": "gis_adapter_import_bypasses_domain_seam",
                        "import": forbidden,
                    }
                )

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
            "compat_shims": sorted(COMPAT_SHIMS),
            "compat_facades": sorted(COMPAT_FACADES),
            "public_modules": sorted(PUBLIC_MODULES),
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
