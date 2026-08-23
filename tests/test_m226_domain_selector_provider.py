import json
import unittest
from unittest import mock

from agent.domain_registry import DomainEntry, DomainRegistry
from agent.domain_selector import (
    CatalogDomainSelector,
    FallbackDomainSelector,
    build_domain_discovery_snapshot,
)
from agent.domain_selector_provider import (
    DomainSelectorProviderError,
    build_domain_selector_provider,
)
from agent.llm_planner import OpenAIPlannerClient
from domains.gis import GIS_DOMAIN_PACK
from domains.text.domain import TEXT_DOMAIN_PACK


class _FakeStructuredClient:
    def __init__(self, result=None, error=None, metrics=None):
        self.result = result
        self.error = error
        self.calls = []
        self._metrics = dict(metrics or {})

    def complete_json(self, messages, schema, *, schema_name="task_plan"):
        self.calls.append(
            {"messages": messages, "schema": schema, "schema_name": schema_name}
        )
        if self.error is not None:
            raise self.error
        return self.result

    def metrics(self):
        return dict(self._metrics)


def _snapshot():
    registry = DomainRegistry(
        {
            "gis": DomainEntry("gis", "空间 GIS", "空间分析", lambda: GIS_DOMAIN_PACK),
            "text": DomainEntry("text", "文本分析", "文本处理", lambda: TEXT_DOMAIN_PACK),
        }
    )
    snapshot = build_domain_discovery_snapshot(registry=registry)
    snapshot["private"] = {"api_key": "must-not-leak"}
    snapshot["domains"][0]["tools"] = ["must-not-leak"]
    return snapshot


class M226DomainSelectorProviderTests(unittest.TestCase):
    def test_environment_factory_defaults_to_catalog_and_rejects_unknown_mode(self):
        provider = build_domain_selector_provider(environ={})

        self.assertEqual(provider.mode, "catalog")
        self.assertIsInstance(provider.selector, CatalogDomainSelector)
        self.assertEqual(provider.status()["status"], "ready")

        with self.assertRaises(DomainSelectorProviderError) as raised:
            build_domain_selector_provider(environ={"SPATIAL_AGENT_DOMAIN_SELECTOR_MODE": "other"})
        self.assertEqual(raised.exception.code, "invalid_domain_selector_mode")

    def test_model_mode_sends_only_safe_discovery_and_request_with_identity_schema(self):
        client = _FakeStructuredClient(
            {"status": "selected", "domain_id": "text", "capability_ids": ["text_summary"]}
        )
        provider = build_domain_selector_provider(
            environ={"SPATIAL_AGENT_DOMAIN_SELECTOR_MODE": "model"},
            client=client,
        )

        decision = provider.select("请生成文本摘要", _snapshot())

        self.assertIsInstance(provider.selector, FallbackDomainSelector)
        self.assertEqual(decision.selection.domain_id, "text")
        call = client.calls[0]
        self.assertEqual(call["schema_name"], "domain_selection_identity")
        self.assertFalse(call["schema"]["additionalProperties"])
        user_payload = json.loads(call["messages"][1]["content"])
        self.assertEqual(set(user_payload), {"discovery", "request"})
        self.assertEqual(user_payload["request"], "请生成文本摘要")
        serialized = json.dumps(user_payload, ensure_ascii=False)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("tools", serialized)

    def test_model_failures_and_unknown_identities_fall_back_to_catalog(self):
        cases = (
            _FakeStructuredClient(error=TimeoutError("private timeout detail")),
            _FakeStructuredClient(result="not-an-object"),
            _FakeStructuredClient(
                {"status": "selected", "domain_id": "private-domain", "capability_ids": []}
            ),
        )
        for client in cases:
            with self.subTest(result=client.result, error=type(client.error).__name__):
                provider = build_domain_selector_provider(mode="model", client=client)
                decision = provider.select("请生成文本摘要", _snapshot())
                self.assertEqual(decision.selection.domain_id, "text")
                self.assertEqual(decision.selector_id, "fallback.v1")
                self.assertTrue(decision.reason_code.startswith("selector_fallback:"))
                self.assertNotIn("private timeout detail", decision.reason_code)

    def test_status_and_metrics_are_bounded_and_exclude_private_configuration(self):
        client = _FakeStructuredClient(
            {"status": "invented"},
            metrics={
                "status": "error",
                "attempts": 1,
                "latency_ms": 2.5,
                "api_key": "secret-key",
                "base_url": "https://private.example",
                "raw_response": "private body",
            },
        )
        provider = build_domain_selector_provider(
            mode="model",
            client=client,
            environ={
                "OPENAI_API_KEY": "secret-key",
                "OPENAI_BASE_URL": "https://private.example",
            },
        )

        provider.select("请生成文本摘要", _snapshot())
        public = json.dumps(
            {"status": provider.status(), "metrics": provider.metrics()},
            ensure_ascii=False,
        )

        self.assertNotIn("secret-key", public)
        self.assertNotIn("private.example", public)
        self.assertNotIn("private body", public)
        self.assertEqual(provider.metrics()["fallbacks"], 1)
        self.assertEqual(provider.metrics()["client"]["attempts"], 1)

    def test_openai_structured_transport_accepts_a_bounded_schema_name(self):
        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps({"output_text": "{\"status\":\"unmatched\"}"}).encode()

        captured = {}

        def urlopen(request, timeout):
            del timeout
            captured.update(json.loads(request.data.decode()))
            return _Response()

        client = OpenAIPlannerClient(
            api_key="test-key",
            model="test-model",
            wire_api="responses",
            max_retries=0,
        )
        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            result = client.complete_json(
                [],
                {"type": "object", "additionalProperties": False},
                schema_name="domain_selection_identity",
            )

        self.assertEqual(result, {"status": "unmatched"})
        self.assertEqual(
            captured["text"]["format"]["name"],
            "domain_selection_identity",
        )


if __name__ == "__main__":
    unittest.main()
