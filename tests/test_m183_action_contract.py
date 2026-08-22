import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from evaluation.contract_harness import (
    compare_action_receipts,
    normalize_action_receipt_contract,
)


class M183ActionContractTests(unittest.TestCase):
    def test_action_receipt_contract_is_transport_neutral_but_detects_semantic_drift(self):
        first = {
            "action_receipt": {
                "schema_version": "spatial-agent.action-receipt.v1",
                "status": "COMPLETED",
                "action_id": "cancel",
                "action_kind": "lifecycle",
                "subject": {"kind": "run", "id": "run-a"},
                "result_ref": {"kind": "run", "id": "run-a"},
                "idempotency_key": "m183-action-1",
                "input_fingerprint": "sha256:abc",
                "reused": False,
            }
        }
        recovered = {
            **first,
            "action_receipt": {
                **first["action_receipt"],
                "subject": {"kind": "run", "id": "run-b"},
                "result_ref": {"kind": "run", "id": "run-b"},
                "reused": True,
            },
        }
        drifted = {
            **recovered,
            "action_receipt": {
                **recovered["action_receipt"],
                "input_fingerprint": "sha256:changed",
            },
        }

        self.assertEqual(compare_action_receipts([first, recovered]), [])
        self.assertTrue(compare_action_receipts([first, drifted]))
        self.assertEqual(
            normalize_action_receipt_contract(first).as_dict()["action_id"],
            "cancel",
        )

    def test_service_artifact_and_history_share_the_action_contract(self):
        with tempfile.TemporaryDirectory(prefix="m183-action-contract-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
            )
            try:
                waiting = service.run(
                    "查询DEM栅格元数据",
                    session_id="m183-contract",
                    require_confirmation=True,
                    export_artifact=True,
                )
                response = service.cancel(
                    waiting["run_id"],
                    idempotency_key="m183-contract-1",
                )
                artifact = store.read_run(response["run_id"], domain_id="gis")
                history = next(
                    item
                    for item in service.list_runs()["runs"]
                    if item["run_id"] == response["run_id"]
                )
            finally:
                service.close()

        self.assertEqual(
            compare_action_receipts([response, artifact, history]), []
        )


if __name__ == "__main__":
    unittest.main()
