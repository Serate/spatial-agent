import argparse
import json

from agent.runtime_factory import build_runtime


def parse_args():
    parser = argparse.ArgumentParser(description="Run the spatial Agent Runtime demo.")
    parser.add_argument(
        "request",
        nargs="*",
        help="Spatial analysis request. Defaults to the M1 road/slope example.",
    )
    parser.add_argument(
        "--planner",
        choices=("rule", "openai"),
        default="rule",
        help="Planner Adapter to use. openai requires OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--backend",
        choices=("memory", "local"),
        default="memory",
        help="Spatial backend to use. local reads configured datasets where supported.",
    )
    parser.add_argument(
        "--session-id",
        default="default",
        help="Conversation session id used when follow-up turns are provided.",
    )
    parser.add_argument(
        "--follow-up",
        action="append",
        default=[],
        help="Additional user turn to run in the same session. Can be passed multiple times.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    request = " ".join(args.request) or "查询距离主干道500米以内、坡度超过25度的区域。"
    runtime = build_runtime(args.planner, args.backend)
    result = runtime.run(request, session_id=args.session_id)
    if args.follow_up:
        results = [result.to_dict()]
        for follow_up in args.follow_up:
            results.append(runtime.run(follow_up, session_id=args.session_id).to_dict())
        print(json.dumps(results, ensure_ascii=True, indent=2))
    else:
        print(json.dumps(result.to_dict(), ensure_ascii=True, indent=2))
