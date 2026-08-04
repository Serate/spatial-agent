import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from agent.service import AgentService


GENERIC_ADMIN_QUERY = "\u67e5\u8be2\u884c\u653f\u533a\u8fb9\u754c"
ADMIN_NAME = "\u6d2a\u5c71\u533a"
ROAD_SLOPE_QUERY = "\u67e5\u8be2\u8ddd\u79bb\u4e3b\u5e72\u9053500\u7c73\u4ee5\u5185\u3001\u5761\u5ea6\u8d85\u8fc725\u5ea6\u7684\u533a\u57df\u3002"
DEM_METADATA_QUERY = "\u67e5\u8be2DEM\u6805\u683c\u5143\u6570\u636e"


def main() -> int:
    checks = []
    if os.environ.get("SPATIAL_AGENT_SMOKE_NESTED") != "1":
        checks.append(_run_unit_tests())
    checks.append(_run_service_smoke())
    report = {
        "status": "ok" if all(item["ok"] for item in checks) else "failed",
        "checks": checks,
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "ok" else 1


def _run_unit_tests():
    env = os.environ.copy()
    env["SPATIAL_AGENT_SMOKE_NESTED"] = "1"
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    return {
        "name": "unit_tests",
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }


def _run_service_smoke():
    service = AgentService()
    road_result = service.run(ROAD_SLOPE_QUERY, session_id="smoke-road")
    raster_result = service.run(DEM_METADATA_QUERY, session_id="smoke-raster")
    first = service.run(GENERIC_ADMIN_QUERY, session_id="smoke-admin")
    second = service.run(ADMIN_NAME, session_id="smoke-admin")
    ok = (
        road_result["status"] == "COMPLETED"
        and raster_result["status"] == "COMPLETED"
        and first["status"] == "NEEDS_CLARIFICATION"
        and second["status"] == "COMPLETED"
        and "memory://range/admin_areas" in second["answer"]
        and raster_result["steps"][0]["tool"] == "get_raster_metadata"
    )
    return {
        "name": "agent_service_smoke",
        "ok": ok,
        "road_status": road_result["status"],
        "raster_status": raster_result["status"],
        "clarification_status": first["status"],
        "follow_up_status": second["status"],
    }


def _tail(value: str, max_lines: int = 20) -> str:
    return "\n".join(value.splitlines()[-max_lines:])


if __name__ == "__main__":
    raise SystemExit(main())
