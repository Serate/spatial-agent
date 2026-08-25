"""Explicit Docker acceptance for a real GIS + Economic orphan restart."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

import production_api
from agent.application.composite import CompositeApplication
from agent.application.composite_runs import CompositeRunApplication


REQUEST = {
    "schema_version": "spatial-agent.composite-request.v1",
    "request": "请同时查询武汉市洪山区行政区边界和GDP最新值",
    "components": [
        {
            "component_id": "space",
            "domain_id": "gis",
            "request": "查询武汉市洪山区行政区边界",
            "planner": "rule",
            "backend": "local",
        },
        {
            "component_id": "economy",
            "domain_id": "economic",
            "request": "查询武汉市洪山区GDP最新值",
            "planner": "rule",
            "backend": "local",
        },
    ],
}


def run_acceptance() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="spatial-agent-m280-") as root:
        database = str(Path(root) / "runs.db")
        artifact_root = str(Path(root) / "artifacts")
        first = CompositeRunApplication(
            coordinator=CompositeApplication(host=production_api.host),
            state_db_path=database,
            artifact_root=artifact_root,
            worker_count=1,
        )
        try:
            # Leave a durable claimed job behind, as if the owner disappeared.
            first._async._schedule = lambda _payload: None
            submitted = first.submit_async(
                REQUEST,
                session_id="m280-real-restart",
                idempotency_key="m280-real-restart-1",
            )
            run_id = submitted["run_id"]
        finally:
            first.close()

        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE async_jobs SET owner_pid = ?, status = 'RUNNING' "
                "WHERE run_id = ?",
                (999999, run_id),
            )
            connection.commit()

        second = CompositeRunApplication(
            coordinator=CompositeApplication(host=production_api.host),
            state_db_path=database,
            artifact_root=artifact_root,
            worker_count=1,
        )
        try:
            observation: dict[str, object] = {}
            detail: dict[str, object] | None = None
            deadline = time.time() + 90
            while time.time() < deadline:
                observation = second.get_observability(run_id)
                if observation.get("status") in {"COMPLETED", "FAILED", "BLOCKED"}:
                    detail = second.get_run(run_id)
                    break
                time.sleep(0.1)
            return {
                "submitted_status": submitted.get("status"),
                "status": observation.get("status"),
                "recovered": bool(observation.get("recovered")),
                "recovery_count": observation.get("recovery_count"),
                "result_type": (detail or {}).get("result", {}).get("type")
                if isinstance((detail or {}).get("result"), dict)
                else None,
                "components": [
                    {
                        "component_id": component.get("component_id"),
                        "state": component.get("state"),
                        "status": component.get("status"),
                    }
                    for component in ((detail or {}).get("components") or [])
                    if isinstance(component, dict)
                ],
            }
        finally:
            second.close()


if __name__ == "__main__":
    print(json.dumps(run_acceptance(), ensure_ascii=True))
