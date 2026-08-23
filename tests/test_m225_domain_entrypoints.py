"""M225: compact contract checks for automatic Domain entry points."""

from __future__ import annotations

import hashlib
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from agent.domain_selector import (
    DomainRouter,
    DomainRoutingCandidate,
    DomainRoutingDecision,
)
from agent.domain_routing_entry import DomainRoutingApplication, DomainRoutingState
from serve_api import AgentApiHandler


class _Router:
    def __init__(self):
        self._router = DomainRouter()

    def catalog(self):
        return self._router.catalog()

    def route(self, request, *, domain_id=None):
        if request == "ambiguous":
            return DomainRoutingDecision(
                decision_id="decision-ambiguous",
                status="ambiguous",
                reason_code="multiple_domain_matches",
                selector_id="fixture.v1",
                request_fingerprint=hashlib.sha256(request.encode()).hexdigest(),
                candidates=(
                    DomainRoutingCandidate("gis", "空间 GIS", score=90),
                    DomainRoutingCandidate("text", "文本分析", score=85),
                ),
            )
        return self._router.route(request, domain_id=domain_id)

    def restore(self, request, domain_id, *, parent_decision_id=None):
        return self._router.restore(
            request,
            domain_id,
            parent_decision_id=parent_decision_id,
        )

    def override(self, prior, domain_id):
        return self._router.override(prior, domain_id)

    def resolve(self, decision):
        return self._router.resolve(decision)


class _Service:
    def __init__(self, domain_id, calls):
        self.domain_id = domain_id
        self.calls = calls

    def run(self, **kwargs):
        self.calls.append(("sync", self.domain_id, kwargs))
        return {
            "status": "COMPLETED",
            "domain_id": self.domain_id,
            "request": kwargs["request"],
        }

    def run_async(self, **kwargs):
        self.calls.append(("async", self.domain_id, kwargs))
        return {
            "status": "SUBMITTED",
            "run_id": "async-text-run",
            "domain_id": self.domain_id,
        }

    def clear_session(self, session_id):
        return {"status": "CLEARED", "session_id": session_id}

    def delete_session(self, session_id):
        return {"status": "DELETED", "session_id": session_id}


class _Host:
    def __init__(self):
        self.calls = []
        self.services = {
            domain_id: _Service(domain_id, self.calls)
            for domain_id in ("gis", "text")
        }

    def service(self, selection):
        domain_id = getattr(selection, "domain_id", selection)
        return self.services[domain_id]


class M225DomainEntrypointTests(unittest.TestCase):
    def test_fastapi_declares_domain_routing_and_auto_run_routes(self):
        import production_api

        declared = {
            (method, route.path)
            for route in production_api.app.routes
            for method in (getattr(route, "methods", None) or set())
        }
        self.assertTrue(
            {
                ("GET", "/domain-routing/catalog"),
                ("GET", "/domain-routing/metrics"),
                ("POST", "/domain-routing/select"),
                (
                    "POST",
                    "/domain-routing/decisions/{decision_id}/select",
                ),
                (
                    "POST",
                    "/domain-routing/sessions/{session_id}/clear",
                ),
                ("POST", "/runs/auto"),
                ("POST", "/runs"),
                ("POST", "/domains/{domain_id}/runs"),
            }.issubset(declared)
        )

    def test_dev_entrypoint_routes_without_planning_on_clarification(self):
        router = _Router()
        state = DomainRoutingState()
        host = _Host()
        bound_prior = router.route("ambiguous")
        bound_prior = DomainRoutingDecision(
            **{
                **bound_prior.__dict__,
                "decision_id": "bound-prior",
            }
        )
        state.save(bound_prior, "bound-session")
        state.bind("bound-session", "gis")

        class Handler(AgentApiHandler):
            service = host.services["gis"]

        Handler.host = host
        Handler.routing = DomainRoutingApplication(
            host,
            router=router,
            state=state,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(method, path, payload=None):
            connection = HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=10
            )
            body = None if payload is None else json.dumps(payload).encode()
            headers = {"Content-Type": "application/json"} if body else {}
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            result = json.loads(response.read().decode())
            connection.close()
            return response.status, result

        try:
            catalog_status, catalog = request("GET", "/domain-routing/catalog")
            ambiguous_status, ambiguous = request(
                "POST",
                "/domain-routing/select",
                {"request": "ambiguous", "session_id": "new-session"},
            )
            unmatched_status, unmatched = request(
                "POST",
                "/runs/auto",
                {"request": "计算量子纠缠熵", "session_id": "new-session"},
            )
            selected_status, selected = request(
                "POST",
                "/runs/auto",
                {"request": "请生成文本摘要", "session_id": "text-session"},
            )
            selected_decision_id = selected["domain_routing"]["decision_id"]
            restored_status, restored = request(
                "POST",
                "/runs/auto",
                {"request": "请生成文本摘要", "session_id": "bound-session"},
            )
            async_status, submitted = request(
                "POST",
                "/runs/auto",
                {
                    "request": "请生成文本摘要",
                    "session_id": "async-session",
                    "async": True,
                    "idempotency_key": "m225-async",
                },
            )
            override_status, overridden = request(
                "POST",
                "/domain-routing/decisions/decision-ambiguous/select",
                {"domain_id": "text", "session_id": "new-session"},
            )
            resumed_status, resumed = request(
                "POST",
                "/runs/auto",
                {
                    "request": "do not route again",
                    "session_id": "new-session",
                    "domain_routing_decision_id": overridden["domain_routing"][
                        "decision_id"
                    ],
                },
            )
            mismatch_status, mismatch = request(
                "POST",
                "/domain-routing/decisions/bound-prior/select",
                {"domain_id": "text", "session_id": "bound-session"},
            )
            _, clear_candidate = request(
                "POST",
                "/domain-routing/select",
                {"request": "计算量子纠缠熵", "session_id": "clear-session"},
            )
            clear_decision_id = clear_candidate["domain_routing"]["decision_id"]
            clear_status, cleared = request(
                "POST",
                "/domain-routing/sessions/clear-session/clear",
            )
            cleared_override_status, _ = request(
                "POST",
                f"/domain-routing/decisions/{clear_decision_id}/select",
                {"domain_id": "text", "session_id": "clear-session"},
            )
            bound_clear_status, _ = request(
                "POST",
                "/sessions/text-session/clear",
            )
            stale_decision_status, _ = request(
                "POST",
                f"/domain-routing/decisions/{selected_decision_id}/select",
                {"domain_id": "gis", "session_id": "text-session"},
            )
            after_clear_status, after_clear = request(
                "POST",
                "/runs/auto",
                {"request": "查询DEM栅格元数据", "session_id": "text-session"},
            )
            delete_status, _ = request("DELETE", "/sessions/text-session")
            after_delete_status, after_delete = request(
                "POST",
                "/runs/auto",
                {"request": "查询DEM栅格元数据", "session_id": "text-session"},
            )
            metrics_status, routing_metrics = request(
                "GET",
                "/domain-routing/metrics",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(catalog_status, 200)
        self.assertEqual(catalog["schema_version"], "spatial-agent.domain-discovery.v1")
        self.assertEqual(ambiguous_status, 200)
        interaction = ambiguous["domain_routing_interaction"]
        self.assertEqual(interaction["actions"][0]["id"], "select_domain")
        self.assertEqual(
            interaction["actions"][0]["input_schema"]["properties"]["domain_id"]["enum"],
            ["gis", "text"],
        )
        self.assertEqual(unmatched_status, 200)
        self.assertEqual(unmatched["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(unmatched["domain_routing_interaction"]["actions"], [])
        self.assertNotIn("plan", unmatched)
        self.assertEqual((selected_status, selected["domain_id"]), (200, "text"))
        self.assertEqual((restored_status, restored["domain_id"]), (200, "gis"))
        self.assertEqual(
            restored["domain_routing"]["selection"]["source"], "restored"
        )
        self.assertEqual((async_status, submitted["status"]), (200, "SUBMITTED"))
        self.assertEqual(submitted["domain_id"], "text")
        self.assertEqual(override_status, 200)
        self.assertEqual(
            overridden["domain_routing"]["parent_decision_id"],
            "decision-ambiguous",
        )
        self.assertEqual(resumed_status, 200)
        self.assertEqual(
            resumed["domain_routing"]["decision_id"],
            overridden["domain_routing"]["decision_id"],
        )
        self.assertEqual((mismatch_status, mismatch["error_code"]), (400, "session_domain_mismatch"))
        self.assertEqual((clear_status, cleared["status"]), (200, "CLEARED"))
        self.assertEqual(cleared_override_status, 404)
        self.assertEqual(bound_clear_status, 200)
        self.assertEqual(stale_decision_status, 404)
        self.assertEqual((after_clear_status, after_clear["domain_id"]), (200, "text"))
        self.assertEqual(delete_status, 200)
        self.assertEqual((after_delete_status, after_delete["domain_id"]), (200, "gis"))
        self.assertEqual(metrics_status, 200)
        self.assertEqual(
            routing_metrics["schema_version"],
            "spatial-agent.domain-routing-metrics.v1",
        )
        self.assertGreater(routing_metrics["selection_count"], 0)
        self.assertNotIn(
            "查询DEM栅格元数据",
            json.dumps(routing_metrics, ensure_ascii=False),
        )
        self.assertEqual(
            [(item[0], item[1]) for item in host.calls],
            [
                ("sync", "text"),
                ("sync", "gis"),
                ("async", "text"),
                ("sync", "text"),
                ("sync", "text"),
                ("sync", "gis"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
