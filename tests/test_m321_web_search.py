"""Compact M321 contracts for allowlisted web search."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from agent.network import WebSearchAdapter, WebSearchConfig, web_search_tool_definition
from agent.react import ReactLoop, ReactToolOutcome
from agent.react.contracts import REACT_DECISION_SCHEMA_VERSION
from agent.runtime_factory import build_runtime, build_runtime_context_snapshot
from agent.tools import ToolRegistry


class _Response:
    def __init__(self, body: bytes, *, url: str, content_type: str = "application/json"):
        self._body = body
        self._url = url
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        }
        self.closed = False

    def geturl(self):
        return self._url

    def read(self, size=-1):
        return self._body if size < 0 else self._body[:size]

    def close(self):
        self.closed = True


class _Opener:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return self.response


def _decision(action, **values):
    return {
        "schema_version": REACT_DECISION_SCHEMA_VERSION,
        "action": action,
        **values,
    }


class M321WebSearchAdapterTests(unittest.TestCase):
    def test_allowlisted_json_sources_are_bounded_and_projected(self):
        response = _Response(
            json.dumps(
                {
                    "results": [
                        {
                            "title": "公开来源",
                            "url": "https://www.gov.cn/data?id=1#fragment",
                            "snippet": "可供回答使用的摘要",
                            "secret": "must-not-leak",
                        },
                        {"title": "越权来源", "url": "https://evil.example/data"},
                    ]
                }
            ).encode("utf-8"),
            url="https://search.example/query",
        )
        opener = _Opener(response)
        adapter = WebSearchAdapter(
            WebSearchConfig(
                provider_url="https://search.example/query",
                allowed_domains=("search.example", "gov.cn"),
            ),
            opener=opener,
        )

        result = adapter.search("洪山区 经济", domains=["gov.cn"], max_results=4)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["reason_code"], "search_completed")
        self.assertEqual(result["source_count"], 1)
        self.assertEqual(result["sources"][0]["domain"], "www.gov.cn")
        self.assertNotIn("secret", str(result))
        self.assertEqual(opener.calls[0][0].method, "GET")
        self.assertIn("q=", opener.calls[0][0].full_url)
        self.assertTrue(response.closed)

    def test_empty_allowlist_fails_closed_without_opening_network(self):
        opener = _Opener(_Response(b"{}", url="https://search.example/query"))
        adapter = WebSearchAdapter(
            WebSearchConfig(provider_url="https://search.example/query"),
            opener=opener,
        )

        result = adapter.search("公开资料")

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason_code"], "search_allowlist_empty")
        self.assertEqual(opener.calls, [])

    def test_provider_redirect_and_oversized_response_are_blocked(self):
        redirected = _Opener(
            _Response(
                b"{}",
                url="https://outside.example/query",
            )
        )
        adapter = WebSearchAdapter(
            WebSearchConfig(
                provider_url="https://search.example/query",
                allowed_domains=("search.example", "gov.cn"),
            ),
            opener=redirected,
        )
        self.assertEqual(
            adapter.search("资料")["reason_code"],
            "search_redirect_not_allowlisted",
        )

        oversized = _Opener(
            _Response(
                b"0123456789",
                url="https://search.example/query",
                content_type="text/html",
            )
        )
        adapter = WebSearchAdapter(
            WebSearchConfig(
                provider_url="https://search.example/query",
                allowed_domains=("search.example",),
                max_response_bytes=5,
            ),
            opener=oversized,
        )
        self.assertEqual(
            adapter.search("资料")["reason_code"],
            "search_response_too_large",
        )

    def test_html_results_only_keep_allowlisted_https_sources(self):
        html = """
        <div class='result'>
          <a class='result__a' href='https://gov.cn/report'>公开报告</a>
          <div class='result__snippet'>报告摘要</div>
        </div>
        """.encode("utf-8")
        adapter = WebSearchAdapter(
            WebSearchConfig(
                provider_url="https://search.example/query",
                allowed_domains=("search.example", "gov.cn"),
            ),
            opener=_Opener(
                _Response(
                    html,
                    url="https://search.example/query",
                    content_type="text/html",
                )
            ),
        )

        result = adapter.search("报告")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["sources"][0]["title"], "公开报告")
        self.assertEqual(result["sources"][0]["snippet"], "报告摘要")


class M321WebSearchIntegrationTests(unittest.TestCase):
    def test_tool_definition_and_factory_registry_are_present(self):
        definition = web_search_tool_definition()
        self.assertEqual(definition["name"], "web_search")
        self.assertEqual(
            definition["output_schema"]["properties"]["result_type"]["const"],
            "document_evidence",
        )
        with patch.dict(
            os.environ,
            {
                "SPATIAL_AGENT_WEB_SEARCH_ENABLED": "1",
                "SPATIAL_AGENT_WEB_SEARCH_URL": "",
                "SPATIAL_AGENT_WEB_ALLOWED_DOMAINS": "",
            },
            clear=False,
        ):
            runtime = build_runtime("rule", "memory")
        self.assertIn("web_search", runtime._registry.names)
        result = runtime._registry.invoke("web_search", {"query": "公开资料"})
        self.assertEqual(result["result_type"], "document_evidence")
        self.assertEqual(result["reason_code"], "search_allowlist_empty")

    def test_openai_planner_receives_registered_search_tool(self):
        class _Client:
            supports_react = True

            def complete_json(self, messages, schema, *, schema_name=None):
                del messages, schema, schema_name
                return _decision("finish", summary="已完成", output_type="direct_answer")

        with patch("agent.runtime_factory.load_openai_config", return_value={}), patch(
            "agent.runtime_factory.OpenAIPlannerClient", return_value=_Client()
        ), patch("agent.runtime_factory.load_answer_generation_config", return_value={}):
            runtime = build_runtime("openai", "memory")
        self.assertIn("web_search", runtime._planner._allowed_tools)

    def test_submission_context_counts_dynamic_search_tool(self):
        with patch.dict(
            os.environ,
            {
                "SPATIAL_AGENT_WEB_SEARCH_ENABLED": "1",
                "SPATIAL_AGENT_WEB_SEARCH_URL": "",
                "SPATIAL_AGENT_WEB_ALLOWED_DOMAINS": "",
            },
            clear=False,
        ):
            runtime = build_runtime("rule", "memory")
            snapshot = build_runtime_context_snapshot("rule", "memory")
        self.assertEqual(
            runtime.runtime_context()["tool_provider"]["tool_count"],
            snapshot["tool_provider"]["tool_count"],
        )
        self.assertEqual(runtime.runtime_context()["fingerprint"], snapshot["fingerprint"])

    def test_react_search_uses_injected_executor_and_can_finish(self):
        decisions = [
            _decision("search", query="公开资料", max_results=2),
            _decision("finish", summary="来源已足够", output_type="document_evidence"),
        ]
        calls = []

        def decide(request, **kwargs):
            del request, kwargs
            return decisions.pop(0)

        outcome = ReactLoop(decide, allowed_tools=(), network_enabled=True).run(
            "查找公开资料",
            execute_search=lambda decision, turn, action_id: calls.append(
                (decision["query"], turn, action_id)
            )
            or ReactToolOutcome(
                result={
                    "result_type": "document_evidence",
                    "status": "ok",
                    "source_count": 1,
                },
                result_ref="react-1",
                output_type="document_evidence",
                citation_count=1,
            ),
        )

        self.assertEqual(outcome.state, "finished")
        self.assertEqual(calls[0][0], "公开资料")
        self.assertEqual(outcome.history[0]["action"], "search")
        self.assertEqual(outcome.evidence[0]["reason_code"], "react_search_completed")


if __name__ == "__main__":
    unittest.main()
