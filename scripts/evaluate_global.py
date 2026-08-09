import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.global_runner import run_global_cases
from evaluation.runner import load_cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the global Spatial Agent acceptance matrix.")
    parser.add_argument("--cases", default="evaluation/cases/global-acceptance.json")
    parser.add_argument("--planner", choices=("rule", "openai"), default="rule")
    parser.add_argument("--backend", choices=("memory", "local"), default="memory")
    parser.add_argument("--include-optional", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = run_global_cases(
        load_cases(args.cases),
        planner=args.planner,
        backend=args.backend,
        include_optional=args.include_optional,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    print(encoded)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    return 0 if not args.strict or report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
