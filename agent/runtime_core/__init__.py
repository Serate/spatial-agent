"""Canonical, domain-neutral Runtime implementation seams."""

from .projection import (
    append_execution_degradation_notice,
    blueprint_steps_match,
    capability_evidence_cache_ttl,
    compact_workflow_templates,
    matched_template_ids,
    plan_dag,
    plan_to_dict,
    planner_source,
    replan_context,
    resolve_result_references,
    result_type_for_observability,
    run_duration_ms,
    run_error_category,
    safe_small_mapping,
    unique,
    utc_now,
)

__all__ = [
    "append_execution_degradation_notice",
    "blueprint_steps_match",
    "capability_evidence_cache_ttl",
    "compact_workflow_templates",
    "matched_template_ids",
    "plan_dag",
    "plan_to_dict",
    "planner_source",
    "replan_context",
    "resolve_result_references",
    "result_type_for_observability",
    "run_duration_ms",
    "run_error_category",
    "safe_small_mapping",
    "unique",
    "utc_now",
]
