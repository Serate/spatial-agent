import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.global_runner import run_global_cases
from evaluation.model_evaluation import DEFAULT_MODEL_FIXTURE
from evaluation.runner import load_cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the global Spatial Agent acceptance matrix.")
    parser.add_argument("--cases", default="evaluation/cases/global-acceptance.json")
    parser.add_argument("--planner", choices=("rule", "openai"), default="rule")
    parser.add_argument("--backend", choices=("memory", "local"), default="memory")
    parser.add_argument("--include-optional", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--model-fixture",
        default=str(DEFAULT_MODEL_FIXTURE),
        help="脱敏结构化模型响应 fixture；默认离线回放，不访问网络",
    )
    parser.add_argument(
        "--no-model-evaluation",
        action="store_true",
        help="跳过离线模型计划质量评测",
    )
    args = parser.parse_args()
    report = run_global_cases(
        load_cases(args.cases),
        planner=args.planner,
        backend=args.backend,
        include_optional=args.include_optional,
        model_fixture=None if args.no_model_evaluation else args.model_fixture,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    print(encoded)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    model_ok = report.get("model_evaluation", {}).get("passed", True)
    return 0 if not args.strict or (report["failed"] == 0 and model_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
