import unittest

from agent.data_kinds import DataProfileError, normalize_data_profile
from result_contract import build_result_contract


class M243DataProfileTests(unittest.TestCase):
    def test_profile_is_bounded_and_deduplicated(self):
        profile = normalize_data_profile({
            "schema_version": "spatial-agent.data-profile.v1",
            "primary": "metrics",
            "kinds": ["metrics", "vector", "metrics"],
        })

        self.assertEqual(profile["primary"], "metrics")
        self.assertEqual(profile["kinds"], ["metrics", "vector"])

    def test_legacy_result_without_profile_is_unknown(self):
        profile = normalize_data_profile(None)
        self.assertEqual(profile["primary"], "unknown")
        self.assertEqual(profile["kinds"], ["unknown"])

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(DataProfileError):
            normalize_data_profile({"kinds": ["economic_magic"]})

    def test_text_domain_declares_document_evidence_shape(self):
        from domains.text.runtime import build_text_runtime

        runtime = build_text_runtime()
        run = runtime.run("请摘要这段文本。")
        result = build_result_contract(
            {**run.to_dict(), "result_type": run.plan.output["type"]},
            registry=runtime.result_registry(),
        )

        self.assertEqual(result["data_profile"]["primary"], "text")
        self.assertIn("document_evidence", result["data_profile"]["kinds"])


if __name__ == "__main__":
    unittest.main()
