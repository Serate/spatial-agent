"""Compact offline contracts for M333 public web policy and fetch."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.agent_settings import open_agent_defaults
from agent.network import (
    WebAccessPolicy,
    WebFetchAdapter,
    WebFetchConfig,
    web_fetch_tool_definition,
)
from agent.runtime_factory import build_runtime
from agent.runtime_factory import build_general_runtime
from agent.answer_generation import build_answer_context
from agent.models import RunStatus
from agent.models import AgentRunResult, PlanStep, StepRun, TaskPlan
from agent.persistence.artifact_store import ArtifactStore
from agent.persistence.sqlite_store import SQLiteStateStore
from agent.application.http import HTTPApplication
from agent.react.contracts import REACT_DECISION_SCHEMA_VERSION
from agent.runtime import AgentRuntime
from agent.request_model import RequestFacts
from agent.tools import ToolRegistry


class _Response:
    def __init__(self, body: bytes, *, url: str, content_type: str = "text/html"):
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


class _QueuePlanner:
    react_enabled = True
    execution_policy_mode = "react"

    def __init__(self, decisions):
        self.decisions = list(decisions)

    def decide(self, request, **kwargs):
        del request, kwargs
        return self.decisions.pop(0)

    def metrics(self):
        return {"execution_mode": "replay_model", "status": "success"}


class _WebDomain:
    domain_id = "m333-test"

    def capability_catalog(self, *, environment="unknown"):
        return {
            "schema_version": "spatial-agent.capability-catalog.v1",
            "domain_id": self.domain_id,
            "version": "1.0.0",
            "environment": environment,
            "capabilities": [],
            "workflow_templates": {},
            "dataset_groups": {},
        }

    def discover(self, request, request_facts):
        del request, request_facts
        return {"domain_id": self.domain_id, "candidate_ids": [], "candidate_count": 0}

    def extract_request_facts(self, request):
        return RequestFacts(
            text=request,
            admin_name=None,
            tasks=(),
            datasets=(),
            constraints={},
            evidence=("answer",),
        )

    def answer_composer(self):
        class _Composer:
            def compose(self, result):
                return "已读取网页。"

            def compose_failure(self, result):
                return "网页读取未完成。"

        return _Composer()


class _WebDispatchAdapter:
    def __init__(self, fetcher):
        self.fetcher = fetcher

    def invoke(self, name, arguments):
        if name == "web_search":
            source = {
                "title": "公开文章",
                "url": "https://example.com/article",
                "domain": "example.com",
                "snippet": "来源摘要",
            }
            return {
                "schema_version": "spatial-agent.document-evidence.v1",
                "result_type": "document_evidence",
                "status": "ok",
                "query": arguments["query"],
                "sources": [source],
                "source_count": 1,
                "allowed_domains": [],
                "reason_code": "search_completed",
            }
        if name == "web_fetch":
            return self.fetcher.invoke(arguments)
        raise AssertionError(name)


def _decision(action, **values):
    return {
        "schema_version": REACT_DECISION_SCHEMA_VERSION,
        "action": action,
        **values,
    }


def _public_resolver(host, port, **kwargs):
    del port, kwargs
    return [(None, None, None, None, ("93.184.216.34", 443))]


def _private_resolver(host, port, **kwargs):
    del host, port, kwargs
    return [(None, None, None, None, ("127.0.0.1", 443))]


class M333WebPolicyTests(unittest.TestCase):
    def test_modes_and_public_address_gate(self):
        self.assertFalse(WebAccessPolicy("off").check_url("https://example.com").allowed)
        self.assertEqual(
            WebAccessPolicy("allowlist", ("example.com",)).check_url(
                "https://www.example.com/a#fragment"
            ).url,
            "https://www.example.com/a",
        )
        policy = WebAccessPolicy("public", resolver=_public_resolver)
        self.assertTrue(policy.check_url("https://example.com/news").allowed)
        self.assertEqual(
            WebAccessPolicy("public", resolver=_private_resolver)
            .check_url("https://example.com/news")
            .reason_code,
            "web_address_not_public",
        )

    def test_forbidden_scheme_credentials_port_and_literal(self):
        policy = WebAccessPolicy("public", resolver=_public_resolver)
        self.assertEqual(policy.check_url("http://example.com").reason_code, "web_https_required")
        self.assertEqual(
            policy.check_url("https://user:pass@example.com").reason_code,
            "web_credentials_forbidden",
        )
        self.assertEqual(
            policy.check_url("https://example.com:8443").reason_code,
            "web_port_forbidden",
        )
        self.assertEqual(
            policy.check_url("https://127.0.0.1").reason_code,
            "web_host_forbidden",
        )


class M333WebFetchTests(unittest.TestCase):
    def test_html_is_projected_and_model_context_is_private(self):
        body = """
        <html><head><title>公开页面</title><script>secret()</script></head>
        <body><h1>标题</h1><p>正文内容</p><style>hidden</style></body></html>
        """.encode("utf-8")
        response = _Response(body, url="https://example.com/page")
        adapter = WebFetchAdapter(
            WebFetchConfig(mode="public"),
            opener=_Opener(response),
            resolver=_public_resolver,
        )
        result = adapter.fetch("https://example.com/page")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result_type"], "document_evidence")
        self.assertEqual(result["source_count"], 1)
        self.assertEqual(result["title"], "公开页面")
        self.assertIn("正文内容", result["_model_context"]["text"])
        self.assertNotIn("secret()", result["_model_context"]["text"])
        self.assertTrue(response.closed)

    def test_react_search_fetch_keeps_body_transient_and_projects_evidence(self):
        body = (
            "<html><title>文章</title><p>网页正文</p>"
            + ("公开内容" * 1000)
            + "PRIVATE_TAIL</html>"
        ).encode("utf-8")
        fetcher = WebFetchAdapter(
            WebFetchConfig(mode="public"),
            opener=_Opener(_Response(body, url="https://example.com/article")),
            resolver=_public_resolver,
        )
        definitions = {
            "web_search": {
                **web_fetch_tool_definition(),
                "name": "web_search",
                "input_schema": {
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 8},
                    },
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"result_type": {"const": "document_evidence"}},
                    "additionalProperties": True,
                },
            },
            "web_fetch": web_fetch_tool_definition(),
        }
        planner = _QueuePlanner(
            [
                _decision("search", query="公开文章", max_results=1),
                _decision(
                    "call_tool",
                    tool_name="web_fetch",
                    arguments={"url": "https://example.com/article"},
                    output_type="document_evidence",
                ),
                _decision("finish", summary="已读取来源", output_type="document_evidence"),
            ]
        )
        with patch(
            "agent.runtime.open_agent_defaults",
            return_value={
                "react_mode": "full",
                "web_mode": "public",
                "web_search_enabled": True,
                "tool_proposals_enabled": False,
                "react_max_turns": 8,
                "react_max_actions": 12,
            },
        ):
            runtime = AgentRuntime(
                planner,
                ToolRegistry(definitions, _WebDispatchAdapter(fetcher)),
                answer_composer=_WebDomain().answer_composer(),
                planner_name="openai",
                domain_pack=_WebDomain(),
                max_retries=0,
            )
            result = runtime.run("请搜索并读取 https://example.com/article 的公开文章")

        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual(result.steps[0].result["result_type"], "document_evidence")
        self.assertEqual(result.steps[1].result["result_type"], "document_evidence")
        self.assertNotIn("_model_context", result.steps[1].result)
        self.assertIn("网页正文", build_answer_context(result)["web_documents"][0]["text"])
        self.assertNotIn("PRIVATE_TAIL", json.dumps(result.to_dict(), ensure_ascii=False))

    def test_non_html_and_oversized_documents_degrade(self):
        response = _Response(b"{}", url="https://example.com/data", content_type="application/json")
        adapter = WebFetchAdapter(
            WebFetchConfig(mode="public"),
            opener=_Opener(response),
            resolver=_public_resolver,
        )
        self.assertEqual(adapter.fetch("https://example.com/data")["reason_code"], "web_content_type_unsupported")
        response = _Response(b"123456", url="https://example.com/data")
        adapter = WebFetchAdapter(
            WebFetchConfig(mode="public", max_response_bytes=5),
            opener=_Opener(response),
            resolver=_public_resolver,
        )
        self.assertEqual(adapter.fetch("https://example.com/data")["reason_code"], "web_response_too_large")

    def test_definition_and_factory_mode(self):
        definition = web_fetch_tool_definition()
        self.assertEqual(definition["name"], "web_fetch")
        self.assertEqual(definition["output_schema"]["properties"]["result_type"]["const"], "document_evidence")
        with patch.dict(os.environ, {"SPATIAL_AGENT_WEB_MODE": "off"}, clear=False):
            defaults = open_agent_defaults()
            runtime = build_runtime("rule", "memory")
        self.assertEqual(defaults["web_mode"], "off")
        self.assertNotIn("web_fetch", runtime._registry.names)

    def test_general_runtime_registers_shared_document_result_type(self):
        runtime = build_general_runtime("rule", "memory")
        self.assertIn("document_evidence", runtime._execution_policy_resolver._known_result_profiles)

    def test_answer_context_bounds_transient_web_text(self):
        class _Result:
            request = "请总结网页"
            status = type("Status", (), {"value": "COMPLETED"})()
            plan = type("Plan", (), {"goal": "总结网页", "output": {"type": "document_evidence"}, "assumptions": []})()
            steps = []

        result = _Result()
        result._transient_model_context = [
            {"url": "https://example.com/one", "domain": "example.com", "title": "一", "text": "正文" * 5000},
            {"url": "https://example.com/two", "domain": "example.com", "title": "二", "text": "正文" * 5000},
        ]
        context = build_answer_context(result)
        self.assertLessEqual(
            len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))),
            12_000,
        )
        self.assertNotIn("prompt", json.dumps(context, ensure_ascii=False).lower())

    def test_answer_context_hard_limit_for_extreme_step_payload(self):
        class _Step:
            def __init__(self, index):
                self.id = "step-" + str(index)
                self.tool = "custom_tool"
                self.status = "COMPLETED"
                self.error = None
                self.result = {
                    "value_" + str(item): ["x" * 240] * 12
                    for item in range(64)
                }

        class _Result:
            request = "x" * 800
            status = type("Status", (), {"value": "COMPLETED"})()
            plan = type(
                "Plan",
                (),
                {
                    "goal": "y" * 400,
                    "output": {"type": "metrics"},
                    "assumptions": ["z" * 200] * 8,
                },
            )()
            steps = [_Step(index) for index in range(16)]

        context = build_answer_context(_Result())
        self.assertLessEqual(
            len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))),
            12000,
        )

    def test_sqlite_and_artifact_recovery_keep_web_body_transient(self):
        page_body = "恢复后重新读取的网页正文"
        url = "https://example.com/recovery"
        public_result = {
            "schema_version": "spatial-agent.web-fetch.v1",
            "result_type": "document_evidence",
            "status": "ok",
            "url": url,
            "domain": "example.com",
            "source_count": 1,
            "sources": [{"title": "页面", "url": url, "domain": "example.com"}],
            "source_records": [{"title": "页面", "url": url, "domain": "example.com"}],
            "title": "页面",
            "content_length": len(page_body),
            "content_hash": "sha256:test",
            "text_preview": page_body,
            "reason_code": "web_fetch_completed",
        }
        result = AgentRunResult(
            run_id="m333-recovery",
            status=RunStatus.COMPLETED,
            request="请读取 " + url,
            session_id="m333",
            domain_id="m333-test",
            plan=TaskPlan(
                goal="读取网页",
                steps=[PlanStep("step-1", "web_fetch", {"url": url})],
                output={"type": "document_evidence"},
            ),
            steps=[
                StepRun(
                    "step-1",
                    "web_fetch",
                    {"url": url},
                    status="COMPLETED",
                    result=public_result,
                )
            ],
        )
        with tempfile.TemporaryDirectory(prefix="m333-recovery-") as directory:
            database = str(Path(directory) / "state.db")
            artifacts = ArtifactStore(str(Path(directory) / "runs"), legacy_domain_id="m333-test")
            store = SQLiteStateStore(database, legacy_domain_id="m333-test")
            store.save(result)
            artifact_path = artifacts.write_run(result.to_dict())
            artifact_text = Path(artifact_path).read_text(encoding="utf-8")
            self.assertNotIn(page_body, artifact_text)

            restored = store.get(result.run_id, domain_id="m333-test")
            self.assertIsNotNone(restored)
            fetcher = WebFetchAdapter(
                WebFetchConfig(mode="public"),
                opener=_Opener(_Response(
                    ("<html><title>页面</title><p>" + page_body + "</p></html>").encode(),
                    url=url,
                )),
                resolver=_public_resolver,
            )
            runtime = AgentRuntime(
                _QueuePlanner([]),
                ToolRegistry(
                    {"web_fetch": web_fetch_tool_definition()},
                    _WebDispatchAdapter(fetcher),
                ),
                answer_composer=_WebDomain().answer_composer(),
                planner_name="rule",
                domain_pack=_WebDomain(),
                max_retries=0,
            )
            runtime._rehydrate_web_context(restored)
            self.assertEqual(
                restored._transient_model_context[0]["text"],
                page_body,
            )

    def test_http_event_and_run_projections_do_not_require_page_body(self):
        url = "https://example.com/http"
        safe_run = {
            "run_id": "m333-http",
            "status": "COMPLETED",
            "result": {
                "result_type": "document_evidence",
                "status": "ok",
                "url": url,
                "source_count": 1,
                "sources": [{"title": "页面", "url": url, "domain": "example.com"}],
            },
        }

        class _Service:
            def get_run(self, run_id, planner="rule", backend="memory"):
                del planner, backend
                self.run_id = run_id
                return dict(safe_run)

            def list_run_events(self, run_id, *, after=0, limit=100):
                del run_id, after, limit
                return [{
                    "event_id": "m333-event",
                    "run_id": "m333-http",
                    "sequence": 1,
                    "phase": "evidence",
                    "kind": "run_completed",
                    "status": "COMPLETED",
                    "message": "分析已完成",
                    "terminal": True,
                }]

        application = HTTPApplication(_Service())
        run_payload = application.read("run", resource_id="m333-http")
        event_payload = application.read("run_events", resource_id="m333-http")
        encoded = json.dumps(
            {"run": run_payload, "events": event_payload}, ensure_ascii=False
        )
        self.assertNotIn("_model_context", encoded)
        self.assertNotIn("恢复后重新读取的网页正文", encoded)


if __name__ == "__main__":
    unittest.main()
