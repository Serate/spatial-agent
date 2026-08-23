"""M226: compact routing evidence and application observability contracts."""

from __future__ import annotations

import hashlib
import json
import unittest

from agent.domain_routing_entry import DomainRoutingApplication, DomainRoutingState
from agent.domain_routing_evidence import (
    bind_domain_routing_evidence,
    build_domain_routing_evidence,
    normalize_domain_routing_evidence,
)
from agent.domain_selector import (
    DomainRouter,
    DomainRoutingCandidate,
    DomainRoutingDecision,
)


class _Router:
    def __init__(self):
        self._delegate = DomainRouter()

    def catalog(self):
        return self._delegate.catalog()

    def route(self, request, *, domain_id=None):
        if request == "ambiguous":
            return DomainRoutingDecision(
                decision_id="routing-root",
                status="ambiguous",
                reason_code="multiple_domain_matches",
                selector_id="fixture.v1",
                request_fingerprint=hashlib.sha256(request.encode()).hexdigest(),
                candidates=(
                    DomainRoutingCandidate("gis", "GIS", score=90),
                    DomainRoutingCandidate("text", "Text", score=80),
                ),
            )
        return self._delegate.route(request, domain_id=domain_id)

    def restore(self, request, domain_id, *, parent_decision_id=None):
        return self._delegate.restore(
            request,
            domain_id,
            parent_decision_id=parent_decision_id,
        )

    def override(self, prior, domain_id):
        return self._delegate.override(prior, domain_id)

    def resolve(self, decision):
        return self._delegate.resolve(decision)


class _Service:
    def __init__(self, domain_id):
        self.domain_id = domain_id

    def run(self, **kwargs):
        evidence = bind_domain_routing_evidence(
            kwargs["_domain_routing_evidence"],
            run_id="run-sync",
            domain_id=self.domain_id,
        )
        return {
            "status": "COMPLETED",
            "run_id": "run-sync",
            "domain_routing_evidence": evidence,
            "result": {"domain_routing_evidence": evidence},
        }

    def run_async(self, **kwargs):
        evidence = bind_domain_routing_evidence(
            kwargs["_domain_routing_evidence"],
            run_id="run-async",
            domain_id=self.domain_id,
        )
        return {
            "status": "SUBMITTED",
            "run_id": "run-async",
            "domain_routing_evidence": evidence,
        }


class _Host:
    def __init__(self):
        self._services = {item: _Service(item) for item in ("gis", "text")}

    def service(self, selection):
        return self._services[selection.domain_id]


class M226DomainRoutingApplicationTests(unittest.TestCase):
    def test_evidence_is_bounded_bindable_and_fail_closed(self):
        router = DomainRouter()
        decision = router.route("请生成文本摘要")
        evidence = build_domain_routing_evidence(decision)
        bound = bind_domain_routing_evidence(
            evidence,
            run_id="run-1",
            domain_id="text",
        )

        self.assertEqual(bound["binding"]["state"], "execution_bound")
        self.assertEqual(bound["decision"]["selected_domain_id"], "text")
        encoded = json.dumps(bound, ensure_ascii=False)
        self.assertNotIn("请生成文本摘要", encoded)
        self.assertNotIn("reasons", encoded)
        self.assertFalse(
            normalize_domain_routing_evidence(
                {"schema_version": "unknown"}
            )["available"]
        )
        with self.assertRaisesRegex(ValueError, "another domain"):
            bind_domain_routing_evidence(
                evidence,
                run_id="run-1",
                domain_id="gis",
            )

    def test_override_lineage_reaches_execution_without_transport_rebuild(self):
        state = DomainRoutingState()
        application = DomainRoutingApplication(
            _Host(),
            router=_Router(),
            state=state,
        )
        pending = application.select(
            {"request": "ambiguous", "session_id": "conversation-1"}
        )
        selected = application.override(
            pending["domain_routing"]["decision_id"],
            {"domain_id": "text", "session_id": "conversation-1"},
        )
        result = application.run(
            {
                "request": "continue",
                "session_id": "conversation-1",
                "domain_routing_decision_id": selected["domain_routing"][
                    "decision_id"
                ],
            }
        )

        evidence = result["domain_routing_evidence"]
        self.assertEqual(
            [item["decision_id"] for item in evidence["lineage"]["events"]],
            ["routing-root", selected["domain_routing"]["decision_id"]],
        )
        self.assertEqual(evidence, result["result"]["domain_routing_evidence"])
        self.assertEqual(evidence["binding"]["run_id"], "run-sync")

    def test_metrics_are_bounded_and_contain_no_request_text(self):
        application = DomainRoutingApplication(_Host(), router=_Router())

        application.run(
            {"request": "请生成文本摘要", "session_id": "conversation-2"}
        )
        snapshot = application.metrics()

        self.assertEqual(snapshot["selection_count"], 1)
        self.assertEqual(snapshot["status_counts"], {"selected": 1})
        self.assertNotIn("请生成文本摘要", json.dumps(snapshot, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
