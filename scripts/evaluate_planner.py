import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.runner import load_cases, run_cases
from run_demo import build_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a Spatial Agent planner.")
    parser.add_argument(
        "--cases",
        default="evaluation/cases/m0-cases.json",
        help="Evaluation case JSON path.",
    )
    parser.add_argument("--planner", choices=("rule", "openai"), default="rule")
    parser.add_argument("--backend", choices=("memory", "local"), default="memory")
    parser.add_argument("--output", help="Optional JSON report output path.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when any evaluation case fails.",
    )
    args = parser.parse_args()

    report = run_cases(
        build_runtime(args.planner, args.backend),
        load_cases(args.cases),
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    print(encoded)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    return 0 if not args.strict or report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
