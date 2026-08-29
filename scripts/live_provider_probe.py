"""Run one explicit, bounded provider or Composite planning probe."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from agent.llm_planner import OpenAIPlannerClient
from agent.integration.openai_config import load_openai_config
from evaluation.live_provider_probe import (
    run_composite_planning_probe,
    run_provider_probe,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=45.0,
        help="单次 provider 请求和 probe worker 的时限；默认 45 秒",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=128,
        help="模型输出上限；复杂 Composite 规划可显式提高，默认 128",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="明确允许调用真实模型；仍需设置 live 环境变量",
    )
    parser.add_argument(
        "--composite",
        action="store_true",
        help="调用真实 Composite Planner；默认只做 provider connectivity probe",
    )
    parser.add_argument(
        "--request",
        default="请规划一次空间 GIS 与区域指标的组合分析，只选择目录中可用的能力。",
        help="Composite planning probe 的自然语言请求",
    )
    parser.add_argument(
        "--backend",
        default="local",
        help="Composite planning 使用的后端标签；默认 local",
    )
    parser.add_argument(
        "--domains",
        default="gis,economic",
        help="逗号分隔的 Domain ID；默认 gis,economic",
    )
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("provider probe requires --allow-network")
    if os.environ.get("SPATIAL_AGENT_LIVE_OPENAI") != "1":
        parser.error("set SPATIAL_AGENT_LIVE_OPENAI=1")

    config = load_openai_config()
    config["timeout_seconds"] = args.timeout_seconds
    config["max_retries"] = 0
    config["max_output_tokens"] = max(64, min(4096, int(args.max_output_tokens)))
    if args.composite:
        # The production composition root creates the OpenAI client lazily.
        # Pass the complete explicit probe budget through the process
        # environment before importing/using that root; otherwise the CLI
        # flags would only affect the direct connectivity-probe path while the
        # Composite planner kept the production defaults (60s and retries).
        _configure_composite_probe_environment(config)
        from production_api import composite_planning_application

        report = run_composite_planning_probe(
            application=composite_planning_application,
            request=args.request,
            planner_name="openai",
            backend=args.backend,
            domain_ids=tuple(
                value.strip() for value in args.domains.split(",") if value.strip()
            ),
            timeout_seconds=args.timeout_seconds,
            provider_timeout_seconds=config["timeout_seconds"],
            max_retries=config["max_retries"],
        )
    else:
        report = run_provider_probe(
            client_factory=lambda timeout: OpenAIPlannerClient(
                **{**config, "timeout_seconds": timeout}
            ),
            timeout_seconds=args.timeout_seconds,
        )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report.get("passed") else 1


def _configure_composite_probe_environment(config):
    """Forward the explicit live budget to the lazy production composition root."""

    os.environ["OPENAI_TIMEOUT_SECONDS"] = str(config["timeout_seconds"])
    os.environ["OPENAI_MAX_RETRIES"] = str(config["max_retries"])
    os.environ["OPENAI_MAX_OUTPUT_TOKENS"] = str(config["max_output_tokens"])


if __name__ == "__main__":
    raise SystemExit(main())
