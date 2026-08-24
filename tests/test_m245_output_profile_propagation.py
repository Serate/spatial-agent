import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service_async import build_async_result_evidence, normalize_async_result_evidence
from domains.text.runtime import build_text_runtime
from result_contract import build_result_contract


class M245OutputProfilePropagationTests(unittest.TestCase):
    def _contract(self):
        runtime = build_text_runtime()
        run = runtime.run("请摘要这段文本。")
        return run, build_result_contract(
            {**run.to_dict(), "result_type": "text_summary_result"},
            registry=runtime.result_registry(),
        )

    def test_async_projection_preserves_profile(self):
        _, contract = self._contract()

        evidence = build_async_result_evidence(contract, status="COMPLETED")
        restored = normalize_async_result_evidence(evidence, status="COMPLETED")

        self.assertEqual(restored["data_profile"], contract["data_profile"])

    def test_artifact_recovery_preserves_profile(self):
        run, contract = self._contract()
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            payload = {**run.to_dict(), "result_type": "text_summary_result", "result": contract}
            artifact_ref = store.write_run(payload)
            restored = store.read_run(run.run_id)

        self.assertTrue(artifact_ref.endswith(".json"))
        self.assertEqual(restored["result"]["data_profile"], contract["data_profile"])


if __name__ == "__main__":
    unittest.main()
