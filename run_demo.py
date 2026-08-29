import argparse
import json

from agent.persistence.artifact_store import ArtifactStore
from agent.domain_registry import domain_registry
from agent.domain_runtime_host import DomainRuntimeHost
from agent.domain_routing_entry import (
    DomainRoutingApplication,
    routing_state_from_environment,
)
from agent.runtime_factory import build_runtime  # compatibility re-export
from agent.runtime_defaults import product_defaults
from agent.service import AgentService


def parse_args():
    defaults = product_defaults()
    parser = argparse.ArgumentParser(description="Run the spatial Agent Runtime demo.")
    parser.add_argument(
        "request",
        nargs="*",
        help="Spatial analysis request. Defaults to the M1 road/slope example.",
    )
    parser.add_argument(
        "--planner",
        choices=("rule", "openai"),
        default=defaults["planner"],
        help="Planner Adapter to use. Defaults to the real model; rule is the offline path.",
    )
    parser.add_argument(
        "--backend",
        choices=("memory", "local"),
        default=defaults["backend"],
        help="Spatial backend to use. local reads configured datasets where supported.",
    )
    parser.add_argument(
        "--domain",
        choices=(*domain_registry().ids(), "auto"),
        default=None,
        help="Registered Domain Pack or auto. Defaults to SPATIAL_AGENT_DOMAIN or GIS.",
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
    runtime_host = None
    if args.domain == "auto":
        artifact_store = ArtifactStore(args.artifact_root)
        runtime_host = DomainRuntimeHost(
            service_factory=lambda domain_id: AgentService(
                artifact_store=artifact_store,
                domain_id=domain_id,
            )
        )
        routing = DomainRoutingApplication(
            runtime_host,
            state=routing_state_from_environment(),
        )

        def execute(user_request):
            return routing.run(
                {
                    "request": user_request,
                    "session_id": args.session_id,
                    "planner": args.planner,
                    "backend": args.backend,
                    "export_artifact": args.export_artifact,
                    "export_geojson": args.export_geojson,
                }
            )
    else:
        service = AgentService(
            artifact_store=ArtifactStore(args.artifact_root),
            domain_id=args.domain,
        )

        def execute(user_request):
            return service.run(
                user_request,
                session_id=args.session_id,
                planner=args.planner,
                backend=args.backend,
                export_artifact=args.export_artifact,
                export_geojson=args.export_geojson,
            )

    try:
        result = execute(request)
        if args.follow_up and result.get("status") != "NEEDS_CLARIFICATION":
            results = [result]
            results.extend(execute(follow_up) for follow_up in args.follow_up)
            print(json.dumps(results, ensure_ascii=True, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=True, indent=2))
    finally:
        if runtime_host is not None:
            runtime_host.close()
        else:
            service.close()
