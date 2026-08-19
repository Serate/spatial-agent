"""Run bounded Spatial Agent validation profiles.

The project has grown enough that "run every possible test" is no longer a
good default during normal development.  This entrypoint keeps the default gate
very small while preserving service, GIS, live, Docker, and full regression
checks as explicit opt-in gates.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


ROOT = Path(__file__).parents[1]
QUICK_CORE_TESTS = (
    "tests.test_m68_workflow_templates.M68WorkflowTemplateTests."
    "test_template_compiler_binds_constraints_and_result_references",
    "tests.test_m69_workflow_runtime.M69WorkflowRuntimeTests."
    "test_plan_is_rejected_when_selected_template_does_not_allow_it",
    "tests.test_m77_request_model.M77SpatialRequestTests."
    "test_runtime_completes_composed_request_and_composes_actual_results",
)
GIS_CORE_TESTS = (
    "tests.test_m6_geojson_admin_backend.M6GeoJSONAdminBackendTests."
    "test_range_query_filters_by_county_name",
    "tests.test_m15_raster_metadata.M15LocalRasterMetadataTests."
    "test_reads_dem_raster_metadata_without_array_processing",
    "tests.test_m70_analysis_ready.M70AnalysisReadyRasterTests."
    "test_valid_analysis_ready_report_is_exposed_and_required",
)
SHORT_LIVE_CASES = (
    "live-gis-spatial-overview",
    "live-gis-constrained-buildability",
)


@dataclass(frozen=True)
class ProfileCommand:
    name: str
    command: Sequence[str]
    env: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "command": list(self.command),
            "env": dict(self.env),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded validation profiles.")
    parser.add_argument(
        "--profile",
        action="append",
        choices=("quick", "smoke", "stage", "full-stage", "gis-core", "live-short", "docker"),
        default=None,
        help="profile to run; repeatable; default: quick",
    )
    parser.add_argument("--dry-run", action="store_true", help="print commands without executing")
    parser.add_argument("--list", action="store_true", help="list profile definitions")
    parser.add_argument("--live-backend", choices=("local", "memory"), default="local")
    parser.add_argument("--live-output", default=str(_default_live_output()))
    parser.add_argument(
        "--dataset-config",
        help="dataset catalog for GIS/live profiles; overrides SPATIAL_AGENT_DATASET_CONFIG",
    )
    parser.add_argument("--docker-base-url", default="http://127.0.0.1:8088")
    args = parser.parse_args()

    if args.list:
        print(json.dumps(_profile_catalog(args), ensure_ascii=True, indent=2))
        return 0

    profiles = args.profile or ["quick"]
    commands = _commands_for_profiles(profiles, args)
    if args.dry_run:
        print(json.dumps({"profiles": profiles, "commands": [c.as_dict() for c in commands]}, ensure_ascii=True, indent=2))
        return 0

    checks = [_run_command(command) for command in commands]
    report = {
        "status": "ok" if all(item["ok"] for item in checks) else "failed",
        "profiles": profiles,
        "checks": checks,
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "ok" else 1


def _profile_catalog(args: argparse.Namespace) -> Dict[str, object]:
    return {
        "quick": {
            "purpose": "minimal development gate: three core contract tripwires",
            "commands": [c.as_dict() for c in _quick_commands()],
        },
        "smoke": {
            "purpose": "service smoke only; no nested unittest discovery",
            "commands": [c.as_dict() for c in _smoke_commands()],
        },
        "stage": {
            "purpose": "minimal phase gate: quick tripwires plus three offline acceptance cases",
            "commands": [c.as_dict() for c in _stage_commands()],
        },
        "full-stage": {
            "purpose": "explicit heavy phase gate: quick, service smoke, full global evaluation, and model replay",
            "commands": [c.as_dict() for c in _full_stage_commands()],
        },
        "gis-core": {
            "purpose": "sampled real-data GIS gate; run with the GIS Python environment",
            "commands": [c.as_dict() for c in _gis_core_commands()],
        },
        "live-short": {
            "purpose": "two representative live LLM + GIS cases, not the full live matrix",
            "commands": [c.as_dict() for c in _live_short_commands(args)],
        },
        "docker": {
            "purpose": "production API acceptance against an already running container",
            "commands": [c.as_dict() for c in _docker_commands(args)],
        },
    }


def _commands_for_profiles(profiles: Iterable[str], args: argparse.Namespace) -> List[ProfileCommand]:
    commands: List[ProfileCommand] = []
    for profile in profiles:
        if profile == "quick":
            commands.extend(_quick_commands())
        elif profile == "smoke":
            commands.extend(_smoke_commands())
        elif profile == "stage":
            commands.extend(_stage_commands())
        elif profile == "full-stage":
            commands.extend(_full_stage_commands())
        elif profile == "gis-core":
            commands.extend(_gis_core_commands())
        elif profile == "live-short":
            commands.extend(_live_short_commands(args, require_dataset_config=True))
        elif profile == "docker":
            commands.extend(_docker_commands(args))
        else:
            raise ValueError("unknown profile: " + profile)
    return commands


def _quick_commands() -> List[ProfileCommand]:
    return [
        ProfileCommand(
            "core_contract_tripwires",
            [
                sys.executable,
                "-m",
                "unittest",
                *QUICK_CORE_TESTS,
                "-v",
            ],
        ),
    ]


def _smoke_commands() -> List[ProfileCommand]:
    return [
        ProfileCommand(
            "service_smoke",
            [sys.executable, str(ROOT / "scripts" / "smoke_check.py")],
        )
    ]


def _stage_commands() -> List[ProfileCommand]:
    return [
        *_quick_commands(),
        ProfileCommand(
            "stage_acceptance_examples",
            [
                sys.executable,
                str(ROOT / "scripts" / "evaluate_global.py"),
                "--cases",
                str(ROOT / "evaluation" / "cases" / "stage-acceptance.json"),
                "--strict",
                "--no-model-evaluation",
                "--no-model-replay",
            ],
        ),
    ]


def _full_stage_commands() -> List[ProfileCommand]:
    return [
        *_quick_commands(),
        *_smoke_commands(),
        ProfileCommand(
            "strict_global_offline_evaluation",
            [sys.executable, str(ROOT / "scripts" / "evaluate_global.py"), "--strict"],
        ),
    ]


def _gis_core_commands() -> List[ProfileCommand]:
    return [
        ProfileCommand(
            "gis_core_examples",
            [
                sys.executable,
                "-m",
                "unittest",
                *GIS_CORE_TESTS,
                "-v",
            ],
        )
    ]


def _live_short_commands(
    args: argparse.Namespace, *, require_dataset_config: bool = False
) -> List[ProfileCommand]:
    env = {
        "SPATIAL_AGENT_LIVE_OPENAI": "1",
        "OPENAI_TIMEOUT_SECONDS": os.environ.get("OPENAI_TIMEOUT_SECONDS", "45"),
    }
    if args.live_backend == "local":
        env["SPATIAL_AGENT_LIVE_GIS"] = "1"
    configured = args.dataset_config or os.environ.get("SPATIAL_AGENT_DATASET_CONFIG")
    if require_dataset_config and args.live_backend == "local" and not configured:
        raise ValueError(
            "live-short local requires --dataset-config or "
            "SPATIAL_AGENT_DATASET_CONFIG"
        )
    if configured:
        env["SPATIAL_AGENT_DATASET_CONFIG"] = configured
    return [
        ProfileCommand(
            "live_short_llm_gis",
            [
                sys.executable,
                str(ROOT / "scripts" / "live_baseline.py"),
                "--allow-network",
                "--backend",
                args.live_backend,
                "--attempts",
                "1",
                "--case-ids",
                ",".join(SHORT_LIVE_CASES),
                "--output",
                args.live_output,
            ],
            env,
        )
    ]


def _docker_commands(args: argparse.Namespace) -> List[ProfileCommand]:
    return [
        ProfileCommand(
            "production_acceptance",
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts" / "production_acceptance.ps1"),
                "-BaseUrl",
                args.docker_base_url,
            ],
        )
    ]


def _run_command(command: ProfileCommand) -> Dict[str, object]:
    env = os.environ.copy()
    env.update(command.env)
    completed = subprocess.run(
        list(command.command),
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    return {
        "name": command.name,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }


def _tail(value: str, max_lines: int = 30) -> str:
    return "\n".join(value.splitlines()[-max_lines:])


def _default_live_output() -> Path:
    base = Path(os.environ.get("SPATIAL_AGENT_TEST_OUTPUT_DIR", tempfile.gettempdir()))
    return base / "spatial-agent-live-short.json"


if __name__ == "__main__":
    raise SystemExit(main())
