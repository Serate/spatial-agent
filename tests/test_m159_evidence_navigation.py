"""M159: the evidence registry remains navigable across history/recovery."""

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.evidence_contract import DOMAIN_EVIDENCE_SCHEMA_VERSION
from agent.result_registry import ResultContractRegistry, ResultTypeSpec
from agent.service import AgentService
from result_contract import build_result_contract
from serve_api import AgentApiHandler


def _payload(run_id="m159-run"):
    return {
        "run_id": run_id,
        "domain_id": "gis",
        "status": "COMPLETED",
        "answer": "已完成。",
        "result_type": "generic_result",
        "plan": {"output": {"type": "generic_result"}, "steps": []},
        "steps": [],
        "plan_evidence": {"available": False},
    }


def _get(port, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, body


class M159EvidenceNavigationTests(unittest.TestCase):
    def test_history_and_artifact_index_expose_same_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(directory)
            payload = _payload()
            contract = build_result_contract(payload)
            path = store.write_run({**payload, "result": contract})
            history = store.list_runs()
            self.assertEqual(history[0]["evidence_registry"], contract["evidence_registry"])
            service = AgentService(artifact_store=store)
            try:
                index = service.get_run_evidence("m159-run")
            finally:
                service.close()
            self.assertEqual(index["evidence_registry"], contract["evidence_registry"])
            self.assertEqual(index["artifact"]["ref"], Path(path).name)

    def test_async_artifact_only_recovery_reuses_top_level_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(directory)
            payload = _payload("m159-async")
            contract = build_result_contract(payload)
            store.write_run({
                **payload,
                "result": contract,
                "evidence_registry": contract["evidence_registry"],
                "_async_requested": True,
            })
            service = AgentService(artifact_store=store)
            try:
                evidence = service.get_async_observability("m159-async")
            finally:
                service.close()
            self.assertEqual(
                evidence["result_evidence"]["evidence_registry"],
                contract["evidence_registry"],
            )

    def test_domain_owned_custom_entry_is_bounded_and_versioned(self):
        registry = ResultContractRegistry(
            {"generic_result": ResultTypeSpec(title="结果")},
            evidence_specs={
                "generic_result": ({
                    "id": "domain_release",
                    "schema_version": DOMAIN_EVIDENCE_SCHEMA_VERSION,
                    "reference": "result.deployment_evidence",
                },),
            },
        )
        contract = build_result_contract(_payload(), registry=registry)
        custom = next(
            item for item in contract["evidence_registry"]["entries"]
            if item["id"] == "domain_release"
        )
        self.assertEqual(custom["schema_version"], DOMAIN_EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(custom["reference"], "result.deployment_evidence")
        self.assertTrue(custom["available"])

    def test_dev_http_exposes_registry_index_and_domain_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ArtifactStore(root)
            payload = _payload()
            contract = build_result_contract(payload)
            store.write_run({**payload, "result": contract})

            class Handler(AgentApiHandler):
                service = AgentService(artifact_store=store)
                artifact_root = root

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                index_status, index_body = _get(
                    server.server_address[1], "/artifacts/runs/m159-run.json/evidence"
                )
                run_status, run_body = _get(
                    server.server_address[1], "/runs/m159-run/evidence"
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                Handler.service.close()
        self.assertEqual(index_status, 200)
        self.assertEqual(run_status, 200)
        self.assertEqual(
            json.loads(index_body)["evidence_registry"],
            json.loads(run_body)["evidence_registry"],
        )
        self.assertEqual(
            json.loads(index_body)["evidence_projection"],
            json.loads(run_body)["evidence_projection"],
        )


if __name__ == "__main__":
    unittest.main()
