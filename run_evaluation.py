import argparse
import json
from pathlib import Path

from evaluation.runner import load_cases, run_cases
from run_demo import build_runtime


def parse_args():
    parser = argparse.ArgumentParser(description="Run Agent evaluation cases.")
    parser.add_argument(
        "--cases",
        default="evaluation/cases/m0-cases.json",
        help="Path to evaluation cases JSON.",
    )
    parser.add_argument(
        "--planner",
        choices=("rule", "openai"),
        default="rule",
        help="Planner Adapter to evaluate.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the evaluation report JSON.",
    )
    parser.add_argument("--environment", default="memory")
    parser.add_argument("--execution-mode", default="offline")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    runtime = build_runtime(args.planner)
    report = run_cases(
        runtime,
        load_cases(args.cases),
        environment=args.environment,
        execution_mode=args.execution_mode,
        planner=args.planner,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
