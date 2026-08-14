"""Run the opt-in live model baseline (M76 core + M79.3 buildability/comparison)."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from agent.service import AgentService
from evaluation.live_baseline import (
    DEFAULT_LIVE_CASES,
    run_live_baseline,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the safe live Spatial Agent baseline.")
    parser.add_argument("--backend", choices=("local", "memory"), default="local")
    parser.add_argument("--max-files", type=int, default=10)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--output")
    parser.add_argument("--case-ids", help="comma-separated case ids; default: all")
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="明确允许调用真实模型；仍需设置 live 环境变量",
    )
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("live baseline requires --allow-network")
    if os.environ.get("SPATIAL_AGENT_LIVE_OPENAI") != "1":
        parser.error("set SPATIAL_AGENT_LIVE_OPENAI=1")
    if args.backend == "local" and os.environ.get("SPATIAL_AGENT_LIVE_GIS") != "1":
        parser.error("set SPATIAL_AGENT_LIVE_GIS=1 for the local GIS backend")

    cases = DEFAULT_LIVE_CASES
    if args.case_ids:
        wanted = {name.strip() for name in args.case_ids.split(",") if name.strip()}
        cases = [case for case in cases if case.get("id") in wanted]

    report = run_live_baseline(
        backend=args.backend,
        max_files=args.max_files,
        attempts_per_case=args.attempts,
        cases=cases,
        service_factory=AgentService,
    )
    encoded = json.dumps(report, ensure_ascii=True, indent=2)
    print(encoded)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
