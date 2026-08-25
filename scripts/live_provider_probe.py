"""Run one explicit, bounded provider connectivity and JSON-shape probe."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from agent.llm_planner import OpenAIPlannerClient
from agent.openai_config import load_openai_config
from evaluation.live_provider_probe import run_provider_probe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=45.0,
        help="单次 provider 请求和 probe worker 的时限；默认 45 秒",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="明确允许调用真实模型；仍需设置 live 环境变量",
    )
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("provider probe requires --allow-network")
    if os.environ.get("SPATIAL_AGENT_LIVE_OPENAI") != "1":
        parser.error("set SPATIAL_AGENT_LIVE_OPENAI=1")

    config = load_openai_config()
    config["timeout_seconds"] = args.timeout_seconds
    config["max_retries"] = 0
    config["max_output_tokens"] = 128
    report = run_provider_probe(
        client_factory=lambda timeout: OpenAIPlannerClient(
            **{**config, "timeout_seconds": timeout}
        ),
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
