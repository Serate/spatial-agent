"""M224-A: one process hosts isolated, versioned Domain runtimes."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from agent.artifact_store import ArtifactStore
from agent.domain_registry import DomainSelectionError
from agent.domain_runtime_host import (
    DOMAIN_SELECTION_SCHEMA_VERSION,
    DomainRuntimeHost,
    DomainSelection,
    resolve_domain_selection,
)
from agent.service import AgentService


class _FakeService:
    def __init__(self, domain_id: str):
        self.domain_id = domain_id
        self.start_reaper_calls = 0
        self.close_calls = 0

    def start_reaper(self) -> None:
        self.start_reaper_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def capabilities(self) -> dict:
        return {"domain_id": self.domain_id}


class _RecordingFactory:
    """Thread-safe factory with a small delay that exposes cache races."""

    def __init__(self):
        self._lock = threading.Lock()
        self.created: list[_FakeService] = []

    def __call__(self, domain_id: str) -> _FakeService:
        time.sleep(0.01)
        service = _FakeService(domain_id)
        with self._lock:
            self.created.append(service)
        return service

    def for_domain(self, domain_id: str) -> list[_FakeService]:
        with self._lock:
            return [item for item in self.created if item.domain_id == domain_id]


class M224DomainSelectionContractTests(unittest.TestCase):
    def test_selection_mapping_round_trips_with_current_schema(self):
        selection = resolve_domain_selection(
            {
                "schema_version": DOMAIN_SELECTION_SCHEMA_VERSION,
                "domain_id": "gis",
            }
        )

        self.assertIsInstance(selection, DomainSelection)
        self.assertEqual(selection.domain_id, "gis")
        self.assertEqual(
            selection.to_dict(),
            {
                "schema_version": DOMAIN_SELECTION_SCHEMA_VERSION,
                "domain_id": "gis",
                "source": "explicit",
            },
        )

    def test_selection_rejects_empty_or_unsupported_version(self):
        invalid_values = (
            {"schema_version": DOMAIN_SELECTION_SCHEMA_VERSION, "domain_id": ""},
            {"schema_version": "future.domain-selection.v99", "domain_id": "gis"},
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    resolve_domain_selection(value)


class M224DomainRuntimeHostLifecycleTests(unittest.TestCase):
    def test_services_are_isolated_and_cached_per_domain(self):
        factory = _RecordingFactory()
        host = DomainRuntimeHost(service_factory=factory)
        try:
            gis = host.service("gis")
            text = host.service("text")

            self.assertIs(gis, host.service("gis"))
            self.assertIs(text, host.service("text"))
            self.assertIsNot(gis, text)
            self.assertEqual([item.domain_id for item in factory.created], ["gis", "text"])
        finally:
            host.close()

    def test_unknown_or_empty_domain_is_rejected(self):
        host = DomainRuntimeHost(service_factory=_RecordingFactory())
        try:
            for domain_id in (None, "", "   ", "unknown"):
                with self.subTest(domain_id=domain_id):
                    with self.assertRaises(DomainSelectionError):
                        host.service(domain_id)
        finally:
            host.close()

    def test_catalog_contains_only_enabled_domains(self):
        host = DomainRuntimeHost(
            service_factory=_RecordingFactory(),
            enabled_domain_ids=("text",),
        )
        try:
            catalog = host.catalog()
        finally:
            host.close()

        self.assertEqual(catalog["domain_ids"], ["text"])
        self.assertEqual([item["id"] for item in catalog["domains"]], ["text"])

    def test_start_prewarms_every_enabled_domain_and_starts_reapers(self):
        factory = _RecordingFactory()
        host = DomainRuntimeHost(
            service_factory=factory,
            enabled_domain_ids=("gis", "text"),
        )
        try:
            host.start()
            host.start()

            self.assertEqual(len(factory.for_domain("gis")), 1)
            self.assertEqual(len(factory.for_domain("text")), 1)
            self.assertEqual(factory.for_domain("gis")[0].start_reaper_calls, 1)
            self.assertEqual(factory.for_domain("text")[0].start_reaper_calls, 1)
        finally:
            host.close()

    def test_close_is_idempotent_and_prevents_future_service_access(self):
        factory = _RecordingFactory()
        host = DomainRuntimeHost(service_factory=factory)
        gis = host.service("gis")
        text = host.service("text")

        host.close()
        host.close()

        self.assertEqual(gis.close_calls, 1)
        self.assertEqual(text.close_calls, 1)
        with self.assertRaises(RuntimeError):
            host.service("gis")

    def test_concurrent_service_lookup_constructs_domain_once(self):
        factory = _RecordingFactory()
        host = DomainRuntimeHost(service_factory=factory)
        try:
            with ThreadPoolExecutor(max_workers=16) as executor:
                services = list(executor.map(host.service, ["gis"] * 32))

            self.assertTrue(all(item is services[0] for item in services))
            self.assertEqual(len(factory.for_domain("gis")), 1)
        finally:
            host.close()


class M224RealAgentServiceContractTests(unittest.TestCase):
    def test_one_host_exposes_correct_gis_and_text_capability_domains(self):
        with tempfile.TemporaryDirectory() as directory:
            def build_service(domain_id: str) -> AgentService:
                return AgentService(
                    artifact_store=ArtifactStore(os.path.join(directory, domain_id)),
                    domain_id=domain_id,
                )

            host = DomainRuntimeHost(service_factory=build_service)
            try:
                gis = host.service("gis").capabilities()
                text = host.service("text").capabilities()
            finally:
                host.close()

        self.assertEqual(gis["domain_id"], "gis")
        self.assertEqual(text["domain_id"], "text")


if __name__ == "__main__":
    unittest.main()
