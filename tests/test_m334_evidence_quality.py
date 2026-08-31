"""Compact M334 contracts for source identity and quality."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from agent.evidence.identity import (
    SOURCE_IDENTITY_SCHEMA_VERSION,
    build_source_identity,
    source_dedupe_key,
)
from agent.evidence.quality import (
    SOURCE_QUALITY_SCHEMA_VERSION,
    build_source_quality,
    normalize_source_quality,
    project_source_record,
)
from agent.evidence.bundle import (
    EVIDENCE_BUNDLE_SCHEMA_VERSION,
    build_evidence_bundle,
    evidence_quality_limitations,
    normalize_evidence_bundle,
)
from agent.evidence.projection import project_evidence_projection
from agent.application.service_async import (
    build_async_result_evidence,
    normalize_async_result_evidence,
)
from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from agent.result_summary import build_result_summary
from agent.application.composite_contract import build_composite_result_contract
from agent.runtime_core.projection import append_execution_degradation_notice


class M334EvidenceIdentityTests(unittest.TestCase):
    def test_same_content_deduplicates_across_urls_without_leaking_secrets(self):
        first = build_source_identity(
            {
                "result_type": "document_evidence",
                "url": "https://Example.com/report#part",
                "content_hash": "sha256:" + "a" * 64,
                "title": "报告",
                "secret": "must-not-leak",
            }
        )
        second = build_source_identity(
            {
                "kind": "web",
                "url": "https://mirror.example/report",
                "content_hash": "sha256:" + "a" * 64,
            }
        )

        self.assertEqual(first["schema_version"], SOURCE_IDENTITY_SCHEMA_VERSION)
        self.assertEqual(first["locator"], "https://example.com/report")
        self.assertEqual(source_dedupe_key(first), source_dedupe_key(second))
        self.assertNotIn("secret", str(first))

    def test_dataset_identifier_rejects_local_paths(self):
        identity = build_source_identity({"kind": "raster", "locator": "D:\\data\\dem.tif"})
        self.assertEqual(identity["source_id"], "")
        self.assertIn("source_locator_missing", identity["reason_codes"])


class M334EvidenceQualityTests(unittest.TestCase):
    def test_missing_timestamp_is_unknown_not_fresh(self):
        quality = build_source_quality({"kind": "web", "url": "https://example.com/a"})
        self.assertEqual(quality["schema_version"], SOURCE_QUALITY_SCHEMA_VERSION)
        self.assertEqual(quality["status"], "unknown")
        self.assertEqual(quality["freshness"]["state"], "unknown")

    def test_recent_and_old_sources_are_distinguished(self):
        now = datetime(2026, 8, 31, tzinfo=timezone.utc)
        recent = build_source_quality(
            {"kind": "metrics", "locator": "indicator:demo", "retrieved_at": "2026-08-30T00:00:00Z"},
            now=now,
            freshness_ttl_seconds=7 * 24 * 60 * 60,
        )
        old = build_source_quality(
            {"kind": "metrics", "locator": "indicator:demo", "retrieved_at": "2026-07-01T00:00:00Z"},
            now=now,
            freshness_ttl_seconds=7 * 24 * 60 * 60,
        )
        self.assertEqual(recent["status"], "available")
        self.assertEqual(recent["freshness"]["state"], "fresh")
        self.assertEqual(old["status"], "stale")

    def test_projection_is_bounded_and_normalization_is_safe(self):
        projected = project_source_record(
            {
                "url": "https://example.com/report",
                "title": "公开报告",
                "snippet": "摘要",
                "retrieved_at": "2026-08-30T00:00:00Z",
                "truncated": True,
            },
            now=datetime(2026, 8, 31, tzinfo=timezone.utc),
        )
        normalized = normalize_source_quality(projected["quality"])
        self.assertEqual(projected["url"], "https://example.com/report")
        self.assertEqual(normalized["status"], "partial")
        self.assertEqual(normalized["completeness"], "partial")
        self.assertNotIn("truncated", str(normalized))

    def test_result_summary_exposes_safe_source_quality_metadata(self):
        summary = build_result_summary(
            {
                "status": "COMPLETED",
                "steps": [
                    {
                        "id": "source",
                        "tool": "web_search",
                        "status": "COMPLETED",
                        "result": {
                            "result_type": "document_evidence",
                            "status": "ok",
                            "source_count": 1,
                            "sources": [
                                {
                                    "title": "公开来源",
                                    "url": "https://example.com/report#part",
                                    "snippet": "摘要",
                                    "retrieved_at": "2026-08-30T00:00:00Z",
                                }
                            ],
                        },
                    }
                ],
            }
        )
        source = summary["blocks"][0]["evidence"]["source_records"][0]
        self.assertTrue(source["source_id"].startswith("source-"))
        self.assertEqual(source["kind"], "web")
        self.assertEqual(source["quality"]["freshness"]["state"], "fresh")
        self.assertNotIn("report#part", source["url"])

    def test_bundle_deduplicates_content_and_keeps_quality_summary_bounded(self):
        entries = [
            {
                "kind": "web",
                "url": "https://example.com/report",
                "content_hash": "sha256:" + "b" * 64,
                "retrieved_at": "2026-08-30T00:00:00Z",
            },
            {
                "kind": "web",
                "url": "https://mirror.example/report",
                "content_hash": "sha256:" + "b" * 64,
                "retrieved_at": "2026-08-30T00:00:00Z",
            },
            {"kind": "raster", "locator": "dem:wh", "version": "2026.1"},
        ]
        bundle = build_evidence_bundle(
            entries,
            now=datetime(2026, 8, 31, tzinfo=timezone.utc),
        )
        self.assertEqual(bundle["schema_version"], EVIDENCE_BUNDLE_SCHEMA_VERSION)
        self.assertEqual(bundle["unique_count"], 2)
        self.assertEqual(bundle["duplicate_count"], 1)
        self.assertEqual(bundle["quality_summary"]["freshness_counts"]["fresh"], 1)
        self.assertEqual(bundle["quality_summary"]["freshness_counts"]["unknown"], 1)
        self.assertEqual(normalize_evidence_bundle(bundle), bundle)

    def test_bundle_detects_same_locator_with_different_content(self):
        bundle = build_evidence_bundle(
            [
                {"kind": "web", "url": "https://example.com/report", "content_hash": "sha256:" + "a" * 64},
                {"kind": "web", "url": "https://example.com/report", "content_hash": "sha256:" + "b" * 64},
            ]
        )
        self.assertEqual(bundle["unique_count"], 2)
        self.assertEqual(bundle["conflict_count"], 1)
        self.assertIn("未自动裁决", "".join(evidence_quality_limitations(bundle)))
        self.assertEqual(normalize_evidence_bundle(bundle)["conflict_count"], 1)

    def test_result_summary_keeps_local_sources_and_quality_caveats(self):
        summary = build_result_summary(
            {
                "status": "COMPLETED",
                "steps": [
                    {
                        "id": "local",
                        "tool": "get_raster_metadata",
                        "status": "COMPLETED",
                        "result": {
                            "result_type": "raster_metadata_result",
                            "status": "ok",
                            "evidence": {
                                "available": True,
                                "source_records": [
                                    {"kind": "raster", "locator": "dem:wh", "version": "2026.1"}
                                ],
                            },
                        },
                    }
                ],
            }
        )
        evidence = summary["evidence"]
        self.assertEqual(evidence["evidence_bundle"]["unique_count"], 1)
        self.assertEqual(evidence["evidence_bundle"]["entries"][0]["locator"], "dem:wh")
        self.assertIn("时间", "".join(summary["limitations"]))

    def test_answer_fallback_explains_unknown_source_time(self):
        result = AgentRunResult(
            run_id="m334-answer",
            status=RunStatus.COMPLETED,
            request="汇总来源",
            plan=TaskPlan("汇总来源", [PlanStep("source", "tool", {})], {"type": "text_summary_result"}),
            steps=[
                StepRun(
                    "source",
                    "tool",
                    {},
                    status="COMPLETED",
                    result={
                        "result_type": "document_evidence",
                        "status": "ok",
                        "source_records": [{"url": "https://example.com/report"}],
                    },
                )
            ],
        )
        answer = append_execution_degradation_notice(result, "已整理当前来源。")
        self.assertIn("证据提示", answer)
        self.assertIn("无法判断是否最新", answer)

    def test_shared_evidence_projection_preserves_bundle(self):
        bundle = build_evidence_bundle([{"kind": "raster", "locator": "dem:wh", "version": "2026.1"}])
        projection = project_evidence_projection(
            {"result_summary": {"evidence": {"evidence_bundle": bundle}}}
        )
        self.assertEqual(projection["evidence_bundle"]["entries"][0]["locator"], "dem:wh")

    def test_composite_combines_child_bundles_across_web_and_local_data(self):
        shared = {
            "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
            "available": True,
            "entries": [
                project_source_record(
                    {
                        "kind": "web",
                        "url": "https://example.com/report",
                        "retrieved_at": "2026-08-30T00:00:00Z",
                    },
                    now=datetime(2026, 8, 31, tzinfo=timezone.utc),
                )
            ],
            "unique_count": 1,
            "duplicate_count": 0,
            "duplicates": [],
            "coverage": {"kinds": ["web"], "domains": ["example.com"], "entry_count": 1},
            "quality_summary": {
                "status_counts": {"available": 1, "duplicate": 0, "partial": 0, "stale": 0, "unknown": 0, "unavailable": 0},
                "freshness_counts": {"fresh": 1, "stale": 0, "unknown": 0},
                "completeness_counts": {"complete": 1, "partial": 0, "unknown": 0},
            },
            "limitations": [],
        }
        result = build_composite_result_contract(
            {
                "schema_version": "spatial-agent.composite-request.v1",
                "request": "跨来源分析",
                "components": [
                    {"component_id": "web", "domain_id": "text", "request": "读取网页"},
                    {"component_id": "local", "domain_id": "gis", "request": "读取本地数据"},
                ],
            },
            {
                "web": {
                    "status": "COMPLETED",
                    "result": {
                        "type": "text_result",
                        "data_profile": {"kinds": ["text"]},
                        "result_summary": {
                            "blocks": [
                                {
                                    "block_id": "article",
                                    "kind": "text",
                                    "state": "complete",
                                    "facts": {"headline": "公开报告"},
                                }
                            ],
                            "evidence": {"evidence_bundle": shared},
                        },
                        "analysis_scope": {
                            "geography": "洪山区",
                            "time_start": "2026",
                            "time_end": "2026",
                            "unit": "text",
                        },
                    },
                },
                "local": {
                    "status": "COMPLETED",
                    "result": {
                        "type": "raster_result",
                        "data_profile": {"kinds": ["raster"]},
                        "result_summary": {
                            "blocks": [
                                {
                                    "block_id": "elevation",
                                    "kind": "raster",
                                    "state": "complete",
                                    "facts": {"minimum": 1, "maximum": 2},
                                }
                            ],
                            "evidence": {
                                "evidence_bundle": build_evidence_bundle(
                                    [{
                                        "kind": "raster",
                                        "locator": "dem:wh",
                                        "version": "2026.1",
                                    }]
                                )
                            }
                        },
                        "analysis_scope": {
                            "geography": "洪山区",
                            "time_start": "2026",
                            "time_end": "2026",
                            "unit": "meter",
                        },
                    },
                },
            },
        )
        bundle = result["composite"]["evidence"]["evidence_bundle"]
        self.assertEqual(bundle["unique_count"], 2)
        self.assertEqual(set(bundle["coverage"]["kinds"]), {"web", "raster"})
        self.assertEqual(len(result["composite"]["evidence"]["fact_receipts"]), 2)
        self.assertEqual(result["composite"]["evidence"]["alignment"]["status"], "conflict")

        async_evidence = build_async_result_evidence(result, status="COMPLETED")
        restored = normalize_async_result_evidence(async_evidence, status="COMPLETED")
        self.assertEqual(
            async_evidence["evidence_projection"]["evidence_bundle"],
            restored["evidence_projection"]["evidence_bundle"],
        )
        self.assertEqual(
            async_evidence["evidence_projection"]["alignment"]["status"],
            "conflict",
        )


if __name__ == "__main__":
    unittest.main()
