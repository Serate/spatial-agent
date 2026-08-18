import argparse
import json

from agent.artifact_store import ArtifactStore
from agent.runtime_factory import build_runtime
from agent.service import AgentService


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
    parser.add_argument(
        "--export-artifact",
        action="store_true",
        help="Export a durable run artifact and include artifact_ref in the JSON payload.",
    )
    parser.add_argument(
        "--artifact-root",
        default="outputs/runs",
        help="Directory for exported run artifacts when --export-artifact is used.",
    )
    parser.add_argument(
        "--export-geojson",
        action="store_true",
        help="Export a bounded GeoJSON summary when tool results contain geometry refs.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    request = " ".join(args.request) or "查询距离主干道500米以内、坡度超过25度的区域。"
    service = AgentService(artifact_store=ArtifactStore(args.artifact_root))
    result = service.run(
        request,
        session_id=args.session_id,
        planner=args.planner,
        backend=args.backend,
        export_artifact=args.export_artifact,
        export_geojson=args.export_geojson,
    )
    if args.follow_up:
        results = [result]
        for follow_up in args.follow_up:
            results.append(
                service.run(
                    follow_up,
                    session_id=args.session_id,
                    planner=args.planner,
                    backend=args.backend,
                    export_artifact=args.export_artifact,
                    export_geojson=args.export_geojson,
                )
            )
        print(json.dumps(results, ensure_ascii=True, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=True, indent=2))
