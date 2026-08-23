import json
import unittest

from agent.domain_registry import DomainEntry, DomainRegistry
from agent.domain_selector import (
    CatalogDomainSelector,
    DomainRouter,
    DomainSelectorError,
    FallbackDomainSelector,
    ModelDomainSelector,
    build_domain_routing_interaction,
    build_domain_discovery_snapshot,
)
from domains.gis import GIS_DOMAIN_PACK
from domains.text.domain import TEXT_DOMAIN_PACK


class _FixtureDomainPack:
    domain_id = "fixture"

    def capability_catalog(self, *, environment="unknown"):
        del environment
        return {
            "tools": [{"name": "must_not_leak"}],
            "capabilities": [
                {
                    "id": "fixture_spatial_analysis",
                    "label": "Fixture 空间分析",
                    "description": "用于制造跨领域歧义。",
                    "request_hints": {"phrases": ["综合空间分析"]},
                    "tools": ["must_not_leak"],
                    "input_schema": {"type": "object"},
                },
                {
                    "id": "fixture_extra",
                    "label": "额外能力",
                    "request_hints": {"phrases": ["fixture extra"]},
                    "tool_schema": {"secret": True},
                },
            ],
        }


def _registry():
    fixture = _FixtureDomainPack()
    return DomainRegistry(
        {
            "gis": DomainEntry("gis", "空间 GIS", "空间分析", lambda: GIS_DOMAIN_PACK),
            "text": DomainEntry("text", "文本分析", "文本处理", lambda: TEXT_DOMAIN_PACK),
            "fixture": DomainEntry(
                "fixture", "Fixture", "测试领域", lambda: fixture
            ),
        }
    )


class M225DomainSelectorTests(unittest.TestCase):
    def setUp(self):
        self.registry = _registry()
        self.snapshot = build_domain_discovery_snapshot(registry=self.registry)

    def test_discovery_snapshot_is_bounded_and_excludes_tools_and_schemas(self):
        snapshot = build_domain_discovery_snapshot(
            registry=self.registry,
            environment="x" * 100,
            max_capabilities_per_domain=1,
        )

        self.assertLessEqual(len(snapshot["domains"]), 16)
        self.assertEqual(len(snapshot["environment"]), 32)
        self.assertTrue(all(len(domain["capabilities"]) == 1 for domain in snapshot["domains"]))
        self.assertEqual(
            set(snapshot),
            {"schema_version", "snapshot_id", "environment", "domains"},
        )
        self.assertEqual(
            set(snapshot["domains"][0]),
            {"id", "label", "description", "capabilities"},
        )
        forbidden = {"tools", "tool_schema", "input_schema", "parameters", "args_schema"}

        def keys(value):
            if isinstance(value, dict):
                return set(value).union(*(keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value))
            return set()

        self.assertFalse(forbidden.intersection(keys(snapshot)))

    def test_catalog_selector_uniquely_matches_gis_and_text(self):
        selector = CatalogDomainSelector()

        for request, expected in (
            ("请做区域空间总览", "gis"),
            ("请为这段材料生成文本摘要", "text"),
        ):
            with self.subTest(request=request):
                decision = selector.select(request, self.snapshot)
                self.assertEqual(decision.status, "selected")
                self.assertEqual(decision.selection.domain_id, expected)
                self.assertEqual(decision.reason_code, "unique_domain_match")

    def test_third_domain_exposes_ambiguity_and_unmatched_states(self):
        selector = CatalogDomainSelector()

        ambiguous = selector.select("请进行综合空间分析", self.snapshot)
        unmatched = selector.select("计算量子纠缠熵", self.snapshot)

        self.assertEqual(ambiguous.status, "ambiguous")
        self.assertEqual(
            {candidate.domain_id for candidate in ambiguous.candidates},
            {"fixture", "gis"},
        )
        self.assertTrue(ambiguous.needs_clarification)
        self.assertEqual(unmatched.status, "unmatched")
        self.assertEqual(unmatched.candidates, ())
        self.assertTrue(unmatched.needs_clarification)

        interaction = build_domain_routing_interaction(ambiguous)
        self.assertEqual(interaction["state"], "candidate_selection")
        self.assertEqual(interaction["allowed_actions"], ["select_domain"])
        self.assertEqual(
            set(interaction["actions"][0]["input_schema"]["properties"]["domain_id"]["enum"]),
            {"fixture", "gis"},
        )
        self.assertEqual(build_domain_routing_interaction(unmatched)["actions"], [])

    def test_model_selector_accepts_only_allowlisted_identities(self):
        captured = {}
        dirty_snapshot = dict(self.snapshot)
        dirty_snapshot["tools"] = [{"name": "must_not_leak"}]
        dirty_snapshot["domains"] = [dict(item) for item in self.snapshot["domains"]]
        text_domain = next(item for item in dirty_snapshot["domains"] if item["id"] == "text")
        text_domain["capabilities"] = [dict(item) for item in text_domain["capabilities"]]
        text_domain["capabilities"][0]["input_schema"] = {"secret": True}

        def invoke(payload):
            captured.update(payload)
            return {
                "status": "selected",
                "domain_id": "text",
                "capability_ids": ["text_summary"],
            }

        valid = ModelDomainSelector(
            invoke
        ).select("生成文本摘要", dirty_snapshot)
        self.assertEqual(valid.selection.domain_id, "text")
        self.assertEqual(valid.candidates[0].capability_ids, ("text_summary",))
        model_catalog = json.dumps(captured["catalog"], ensure_ascii=False)
        self.assertNotIn("must_not_leak", model_catalog)
        self.assertNotIn("input_schema", model_catalog)

        invalid_outputs = (
            {"status": "selected", "domain_id": "unknown"},
            {
                "status": "selected",
                "domain_id": "text",
                "capability_ids": ["unknown_capability"],
            },
        )
        for output in invalid_outputs:
            with self.subTest(output=output):
                with self.assertRaises(DomainSelectorError):
                    ModelDomainSelector(lambda _payload, value=output: value).select(
                        "生成文本摘要", self.snapshot
                    )

    def test_invalid_model_output_falls_back_to_catalog_selector(self):
        selector = FallbackDomainSelector(
            ModelDomainSelector(lambda _payload: {"status": "invented"})
        )

        decision = selector.select("请生成文本摘要", self.snapshot)

        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.selection.domain_id, "text")
        self.assertEqual(decision.selector_id, "fallback.v1")
        self.assertEqual(
            decision.reason_code,
            "selector_fallback:invalid_domain_selector_output",
        )

    def test_user_override_preserves_parent_decision_id(self):
        router = DomainRouter(registry=self.registry)
        prior = router.route("请进行综合空间分析")

        overridden = router.override(prior, "text")

        self.assertEqual(prior.status, "ambiguous")
        self.assertEqual(overridden.status, "selected")
        self.assertEqual(overridden.selection.domain_id, "text")
        self.assertEqual(overridden.parent_decision_id, prior.decision_id)
        self.assertEqual(overridden.request_fingerprint, prior.request_fingerprint)
        self.assertEqual(overridden.reason_code, "user_domain_override")

        restored = router.restore(
            "继续刚才的请求",
            "text",
            parent_decision_id=overridden.decision_id,
        )
        self.assertEqual(restored.selection.source, "restored")
        self.assertEqual(restored.parent_decision_id, overridden.decision_id)
        self.assertEqual(restored.reason_code, "session_domain_restored")


if __name__ == "__main__":
    unittest.main()
