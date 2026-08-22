"""Cross-entry result contract harness.

The harness deliberately exposes a small interface to acceptance tests:
normalize a public result, compare two normalized results, and report bounded
field differences.  The implementation hides the compatibility envelope
paths so CLI, HTTP, artifact, and recovery tests do not each invent their own
contract projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

from agent.contract_versions import RUN_ARTIFACT_SCHEMA_VERSION
from agent.action_lifecycle import (
    ACTION_LIFECYCLE_SCHEMA_VERSION,
    LIFECYCLE_ACTIONS,
    LIFECYCLE_STATES,
    project_action_lifecycle,
)
from agent.execution_contract import build_execution_record, execution_record_summary
from agent.runtime_context import normalize_runtime_context
from agent.request_identity import normalize_request_identity
from agent.plan_identity import normalize_plan_identity
from agent.plan_quality import project_plan_quality_evidence
from agent.plan_policy import normalize_plan_policy_evidence
from agent.planner_selection import normalize_planner_selection_evidence
from agent.selection_interaction import normalize_selection_interaction
from agent.workflow_selection import normalize_workflow_selection_evidence
from agent.execution_timeline import normalize_execution_timeline
from agent.action_precondition import (
    ACTION_PRECONDITION_SCHEMA_VERSION,
    normalize_action_preconditions,
    project_action_preconditions,
)
from agent.evidence_registry import (
    normalize_evidence_registry,
    project_evidence_registry_completeness,
)
from agent.evidence_projection import project_evidence_projection
from agent.recovery_action import (
    ACTION_RECEIPT_SCHEMA_VERSION,
    normalize_action_receipt,
)
from agent.action_identity import (
    ACTION_RECEIPT_LINKAGE_SCHEMA_VERSION,
    normalize_action_receipt_identity_linkage as _normalize_action_receipt_identity_linkage,
)


@dataclass(frozen=True)
class CrossEntryContract:
    """Stable, JSON-safe projection of a completed public run result."""

    values: Mapping[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.values)

    def differences(self, other: "CrossEntryContract") -> List[str]:
        return _differences(self.values, other.values)

    def equivalent_to(self, other: "CrossEntryContract") -> bool:
        return not self.differences(other)


@dataclass(frozen=True)
class ActionReceiptContract:
    """Stable semantic projection of one lifecycle action receipt."""

    values: Mapping[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.values)

    def differences(self, other: "ActionReceiptContract") -> List[str]:
        return _differences(self.values, other.values)

    def equivalent_to(self, other: "ActionReceiptContract") -> bool:
        return not self.differences(other)


@dataclass(frozen=True)
class ActionReceiptIdentityLinkageContract:
    """Stable linkage of one action to its run-level identities."""

    values: Mapping[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.values)

    def differences(self, other: "ActionReceiptIdentityLinkageContract") -> List[str]:
        return _differences(self.values, other.values)

    def equivalent_to(self, other: "ActionReceiptIdentityLinkageContract") -> bool:
        return not self.differences(other)


@dataclass(frozen=True)
class ActionTimelineContract:
    """Stable transition projection carried by the execution timeline."""

    values: Mapping[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.values)

    def differences(self, other: "ActionTimelineContract") -> List[str]:
        return _differences(self.values, other.values)

    def equivalent_to(self, other: "ActionTimelineContract") -> bool:
        return not self.differences(other)


@dataclass(frozen=True)
class ActionPreconditionContract:
    """Stable evidence of whether one lifecycle action is executable."""

    values: Mapping[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.values)

    def differences(self, other: "ActionPreconditionContract") -> List[str]:
        return _differences(self.values, other.values)

    def equivalent_to(self, other: "ActionPreconditionContract") -> bool:
        return not self.differences(other)


def normalize_action_receipt_contract(
    payload: Mapping[str, Any],
) -> ActionReceiptContract:
    """Project a receipt while excluding transport-specific run identities.

    The source run/result IDs and the ``reused`` marker describe where and how
    a caller observed an action.  They are not the action's semantic
    contract.  Action kind, state, idempotency input and result/subject kinds
    must remain stable across Service, HTTP, Artifact and history entries.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("action receipt payload must be a mapping")
    raw = payload.get("action_receipt")
    if not isinstance(raw, Mapping) and isinstance(payload.get("result"), Mapping):
        raw = payload["result"].get("action_receipt")
    if not isinstance(raw, Mapping):
        raw = payload
    if not isinstance(raw, Mapping) or not raw:
        return ActionReceiptContract(
            {
                "available": False,
                "schema_version": ACTION_RECEIPT_SCHEMA_VERSION,
            }
        )
    receipt = normalize_action_receipt(raw)
    subject = receipt.get("subject") if isinstance(receipt.get("subject"), Mapping) else {}
    result_ref = receipt.get("result_ref") if isinstance(receipt.get("result_ref"), Mapping) else {}
    values: Dict[str, Any] = {
        "available": True,
        "schema_version": receipt.get("schema_version"),
        "status": receipt.get("status"),
        "action_id": receipt.get("action_id"),
        "action_kind": receipt.get("action_kind"),
        "subject_kind": subject.get("kind"),
        "result_kind": result_ref.get("kind"),
        "idempotency_key": receipt.get("idempotency_key"),
        "input_fingerprint": receipt.get("input_fingerprint"),
    }
    if receipt.get("error_code"):
        values["error_code"] = receipt.get("error_code")
    return ActionReceiptContract(values)


def compare_action_receipts(
    payloads: Sequence[Mapping[str, Any]],
) -> List[str]:
    """Return bounded semantic drift paths for two or more receipt entries."""
    if len(payloads) < 2:
        raise ValueError("at least two action receipts are required")
    contracts = [normalize_action_receipt_contract(item) for item in payloads]
    baseline = contracts[0]
    differences: List[str] = []
    for index, contract in enumerate(contracts[1:], start=1):
        differences.extend(
            f"entry[{index}].{path}"
            for path in baseline.differences(contract)
        )
    return differences


def normalize_action_receipt_identity_linkage(
    payload: Mapping[str, Any],
) -> ActionReceiptIdentityLinkageContract:
    """Project Request/Plan/Result/Evidence linkage independently of action semantics."""
    if not isinstance(payload, Mapping):
        raise ValueError("action receipt linkage payload must be a mapping")
    raw = payload.get("action_receipt")
    if not isinstance(raw, Mapping) and isinstance(payload.get("result"), Mapping):
        raw = payload["result"].get("action_receipt")
    raw_linkage = raw.get("identity_linkage") if isinstance(raw, Mapping) else None
    linkage = _normalize_action_receipt_identity_linkage(raw_linkage)
    if linkage is None:
        return ActionReceiptIdentityLinkageContract(
            {
                "available": False,
                "schema_version": ACTION_RECEIPT_LINKAGE_SCHEMA_VERSION,
            }
        )
    return ActionReceiptIdentityLinkageContract(linkage)


def compare_action_receipt_identity_linkages(
    payloads: Sequence[Mapping[str, Any]],
) -> List[str]:
    """Return bounded linkage drift paths across persistence/transport entries."""
    if len(payloads) < 2:
        raise ValueError("at least two action receipt linkages are required")
    contracts = [normalize_action_receipt_identity_linkage(item) for item in payloads]
    baseline = contracts[0]
    differences: List[str] = []
    for index, contract in enumerate(contracts[1:], start=1):
        differences.extend(
            f"entry[{index}].{path}"
            for path in baseline.differences(contract)
        )
    return differences


def normalize_action_timeline_contract(
    payload: Mapping[str, Any],
) -> ActionTimelineContract:
    """Project action events without transport IDs or replay markers."""

    if not isinstance(payload, Mapping):
        raise ValueError("action timeline payload must be a mapping")
    raw = payload.get("execution_timeline")
    if not isinstance(raw, Mapping) and isinstance(payload.get("result"), Mapping):
        raw = payload["result"].get("execution_timeline")
    timeline = normalize_execution_timeline(raw)
    events = []
    for event in timeline.get("events", []):
        if not isinstance(event, Mapping) or event.get("kind") != "action":
            continue
        linkage = event.get("action_linkage")
        if isinstance(linkage, Mapping):
            # The event itself is already bounded; retain only stable
            # transition semantics and identity linkage.  Subject/result IDs,
            # idempotency and reused markers stay in their own contracts.
            events.append({
                "kind": "action",
                "action_linkage": dict(linkage),
            })
    return ActionTimelineContract({
        "available": bool(events),
        "events": events,
    })


def compare_action_timelines(
    payloads: Sequence[Mapping[str, Any]],
) -> List[str]:
    """Return bounded action-timeline drift across response/recovery entries."""

    if len(payloads) < 2:
        raise ValueError("at least two action timelines are required")
    contracts = [normalize_action_timeline_contract(item) for item in payloads]
    baseline = contracts[0]
    differences: List[str] = []
    for index, contract in enumerate(contracts[1:], start=1):
        differences.extend(
            f"entry[{index}].{path}"
            for path in baseline.differences(contract)
        )
    return differences


def normalize_action_precondition_contract(
    payload: Mapping[str, Any],
) -> ActionPreconditionContract:
    """Normalize preconditions independently of the timeline contract.

    The Action Receipt projection is preferred over stale transport/result
    copies.  This allows HTTP, SQLite, Artifact and async acceptance to report
    exactly which precondition changed without comparing unrelated timeline
    or identity fields.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("action precondition payload must be a mapping")
    result = payload.get("result")
    result = result if isinstance(result, Mapping) else {}
    receipt = payload.get("action_receipt")
    if not isinstance(receipt, Mapping):
        receipt = result.get("action_receipt")
    receipt = receipt if isinstance(receipt, Mapping) else {}
    raw = receipt.get("preconditions")
    if not isinstance(raw, Mapping):
        raw = payload.get("action_preconditions")
    if not isinstance(raw, Mapping):
        raw = result.get("action_preconditions")
    if isinstance(raw, Mapping) and "schema_version" in raw:
        projection = normalize_action_preconditions(raw)
    else:
        projection = project_action_preconditions(payload)
    return ActionPreconditionContract({
        "schema_version": projection.get(
            "schema_version", ACTION_PRECONDITION_SCHEMA_VERSION
        ),
        "available": bool(projection.get("available")),
        "action_id": projection.get("action_id"),
        "state": projection.get("state"),
        "action_allowed": projection.get("action_allowed"),
        "enforcement": projection.get("enforcement"),
        "reason_code": projection.get("reason_code"),
        "condition_count": projection.get("condition_count", 0),
        "conditions": projection.get("conditions", []),
    })


def compare_action_preconditions(
    payloads: Sequence[Mapping[str, Any]],
) -> List[str]:
    """Return bounded precondition drift across public/recovery entries."""
    if len(payloads) < 2:
        raise ValueError("at least two action preconditions are required")
    contracts = [
        normalize_action_precondition_contract(item) for item in payloads
    ]
    baseline = contracts[0]
    differences: List[str] = []
    for index, contract in enumerate(contracts[1:], start=1):
        differences.extend(
            f"entry[{index}].{path}"
            for path in baseline.differences(contract)
        )
    return differences


def normalize_result(payload: Mapping[str, Any]) -> CrossEntryContract:
    """Project one public result onto fields that must survive entry changes.

    The projection intentionally excludes run ids, file paths, timestamps and
    other transport-specific values.  It includes request/planning evidence,
    execution governance, user answer, views and artifact availability—the
    fields that prove the same Agent Runtime contract was used.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("result payload must be a mapping")
    if not isinstance(payload.get("result"), Mapping):
        raise ValueError("result envelope is missing")
    result = _mapping(payload.get("result"))
    if not result.get("type"):
        raise ValueError("result envelope type is missing")
    planning = _mapping(result.get("planning"))
    lineage = _mapping(result.get("lineage"))
    artifact = _mapping(lineage.get("artifact"))
    views = _mapping(result.get("views"))
    panels = _mapping(views.get("panels"))
    workspace = _mapping(result.get("workspace"))
    plan_identity = _mapping(planning.get("plan_identity"))
    request_identity = normalize_request_identity(result.get("request_identity"))
    context = _mapping(payload.get("context_evidence"))
    provenance = _mapping(payload.get("provenance"))
    runtime_context = normalize_runtime_context(
        payload.get("runtime_context")
        if isinstance(payload.get("runtime_context"), Mapping)
        else result.get("runtime_context")
    )
    section_names = context.get("section_names")
    section_names = section_names if isinstance(section_names, list) else []
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    artifact_available = _artifact_available(
        payload,
        result=result,
        artifact=artifact,
    )
    evidence_projection = project_evidence_projection(payload)
    evidence_selection = _mapping(evidence_projection.get("selection"))
    values = {
            "status": payload.get("status"),
            "result_type": result.get("type"),
            "result_title": result.get("title"),
            "answer": payload.get("answer", ""),
            "runtime_context": runtime_context,
            "request_identity": request_identity,
            "model_evidence": result.get("model_evidence"),
            "deployment_evidence": result.get("deployment_evidence"),
            "provenance_context_fingerprint": provenance.get(
                "runtime_context_fingerprint"
            ),
            "planning_source": planning.get("source"),
            "plan_identity_version": plan_identity.get("version"),
            "plan_identity_fingerprint": plan_identity.get("fingerprint"),
            "selected_capability": planning.get("selected_capability_id"),
            "capability_candidates": planning.get("capability_candidate_ids"),
            "capability_catalog_available": planning.get("capability_catalog_available"),
            "capability_catalog_ids": planning.get("capability_catalog_ids"),
            "request_facts": result.get("request_facts"),
            "action_lifecycle": _lifecycle_projection(
                payload, result=result
            ),
            "execution_policy": planning.get("execution_policy"),
            "step_governance": [
                step.get("governance")
                for step in steps
                if isinstance(step, dict)
            ],
            "capability_catalog_environment": planning.get("capability_catalog_environment"),
            "capability_catalog_tool_schema_count": planning.get(
                "capability_catalog_tool_schema_count"
            ),
            "request_understanding_available": planning.get(
                "request_understanding_available"
            ),
            "request_understanding_domain_id": planning.get(
                "request_understanding_domain_id"
            ),
            "request_understanding_schema_version": planning.get(
                "request_understanding_schema_version"
            ),
            "context_has_request_understanding": "request_understanding"
            in section_names,
            "context_has_capability_discovery": "capability_discovery"
            in section_names,
            "context_has_capability_catalog": "capability_catalog"
            in section_names,
            "exact_templates": planning.get("exact_template_ids"),
            "matched_templates": planning.get("matched_template_ids"),
            "plan_quality": project_plan_quality_evidence(planning.get("plan_quality")),
            "planner_selection": normalize_planner_selection_evidence(
                evidence_selection.get("planner_selection")
            ),
            "plan_policy": normalize_plan_policy_evidence(
                planning.get("plan_policy")
            ),
            "workflow_selection": normalize_workflow_selection_evidence(
                evidence_selection.get("workflow_selection")
            ),
            "selection_interaction": _selection_interaction_projection(
                result.get("selection_interaction")
            ),
            "execution_timeline": normalize_execution_timeline(
                result.get("execution_timeline"),
                include_action_events=False,
            ),
            "repair_lineage": _repair_lineage_projection(
                result.get("replanning")
            ),
            "evidence_registry": normalize_evidence_registry(
                evidence_projection.get("evidence_registry")
            ),
            "evidence_registry_completeness": project_evidence_registry_completeness(
                evidence_projection.get("evidence_registry")
            ),
            "evidence_projection": evidence_projection,
            "step_tools": [
                step.get("tool")
                for step in steps
                if isinstance(step, dict)
            ],
            "step_statuses": [
                step.get("status")
                for step in steps
                if isinstance(step, dict)
            ],
            "trace_step_count": len(payload.get("trace_summary") or []),
            "artifact_available": artifact_available,
            "artifact_schema": _artifact_schema(
                payload,
                result=result,
                artifact=artifact,
                artifact_available=artifact_available,
            ),
            "async_result_evidence": _async_result_evidence_projection(payload),
            "degradation_and_view_states": _degradation_and_view_states(
                payload,
                result=result,
                views=views,
            ),
            "workspace_panels": workspace.get("panels", []),
            "views_schema": views.get("schema_version"),
            "view_panels": sorted(str(key) for key in panels),
            "view_kinds": {
                str(key): _mapping(value).get("kind")
                for key, value in sorted(panels.items(), key=lambda item: str(item[0]))
            },
        }
    execution = normalize_execution(payload)
    if execution is not None:
        values["execution"] = execution
    return CrossEntryContract(values)


def _lifecycle_projection(
    payload: Mapping[str, Any], *, result: Mapping[str, Any] | None = None
) -> Dict[str, Any]:
    """Project lifecycle evidence without volatile subject or decision ids."""
    result = result if isinstance(result, Mapping) else {}
    raw = result.get("lifecycle")
    if not isinstance(raw, Mapping):
        raw = payload.get("lifecycle")
    if not isinstance(raw, Mapping) or raw.get("schema_version") != ACTION_LIFECYCLE_SCHEMA_VERSION:
        raw = project_action_lifecycle(payload)
    state = str(raw.get("state") or "failed")[:64]
    if state not in LIFECYCLE_STATES:
        state = "failed"
    actions = [
        str(item)[:32]
        for item in (raw.get("allowed_actions") or [])
        if str(item) in LIFECYCLE_ACTIONS
    ][:8]
    lineage = raw.get("lineage") if isinstance(raw.get("lineage"), Mapping) else {}
    return {
        "schema_version": ACTION_LIFECYCLE_SCHEMA_VERSION,
        "state": state,
        "phase": str(raw.get("phase") or "unknown")[:32],
        "status": str(raw.get("status") or payload.get("status") or "UNKNOWN")[:32],
        "allowed_actions": actions,
        "reason_code": str(raw.get("reason_code") or "")[:96],
        "attempt": _bounded_int(raw.get("attempt"), 1, 10000),
        "lineage": {
            "retry_count": _bounded_int(lineage.get("retry_count"), 0, 10000),
            "repair_count": _bounded_int(lineage.get("repair_count"), 0, 1000),
            "recovery_count": _bounded_int(lineage.get("recovery_count"), 0, 10000),
            "decision": str(lineage.get("decision") or "")[:64] or None,
            "recovered": bool(lineage.get("recovered")),
        },
    }


def _repair_lineage_projection(value: Any) -> Dict[str, Any]:
    """Project repair lineage without volatile timing or provider details.

    The full result envelope may retain bounded latency and occurrence time
    for observability.  Those fields are intentionally excluded here because
    the Contract Harness compares the same semantic run across sync, async,
    HTTP and artifact-only recovery.  Step/tool identities, repair phase,
    outcome and plan-quality transitions are stable evidence and must remain
    comparable across those entries.
    """

    version = "spatial-agent.replanning.v1"
    source = value if isinstance(value, Mapping) else {}
    events = source.get("events") if isinstance(source.get("events"), list) else []
    projected = []
    for event in events[:8]:
        if not isinstance(event, Mapping):
            continue
        failed_step_id = _bounded_contract_text(event.get("failed_step_id"))
        failed_tool = _bounded_contract_text(event.get("failed_tool"))
        if not failed_step_id or not failed_tool:
            continue
        item = {
            "failed_step_id": failed_step_id,
            "failed_tool": failed_tool,
            "failure_category": _bounded_contract_text(
                event.get("failure_category")
            ) or "unknown",
            "replanned_step_ids": [
                token
                for token in (
                    _bounded_contract_text(entry)
                    for entry in (event.get("replanned_step_ids") or [])
                )
                if token
            ][:24],
        }
        phase = _bounded_contract_text(event.get("phase"))
        if phase in {"planning", "execution"}:
            item["phase"] = phase
        repair_status = _bounded_contract_text(event.get("repair_status"))
        if repair_status in {"repaired", "failed"}:
            item["repair_status"] = repair_status
        repair_reason = _bounded_contract_text(event.get("repair_reason_code"))
        if repair_reason:
            item["repair_reason_code"] = repair_reason
        for key in ("plan_quality_before", "plan_quality_after"):
            if isinstance(event.get(key), Mapping):
                item[key] = project_plan_quality_evidence(event[key])
        projected.append(item)
    return {
        "schema_version": version,
        "available": bool(projected),
        "count": len(projected),
        "events": projected,
    }


def _bounded_contract_text(value: Any) -> str:
    """Keep contract identifiers bounded and avoid echoing arbitrary values."""

    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    return str(value).strip()[:96]


def _artifact_schema(
    payload: Mapping[str, Any],
    *,
    result: Mapping[str, Any],
    artifact: Mapping[str, Any],
    artifact_available: bool,
) -> str | None:
    """Return only the artifact format version, never its reference.

    Run artifacts written before M147 intentionally have no version field.
    When lineage proves an artifact is available but the public envelope does
    not carry its top-level version, use the current compatible namespace so
    old and current entries remain comparable.  An explicitly supplied future
    version is still preserved and therefore remains visible to the harness.
    """
    candidates = [
        payload.get("artifact_schema_version"),
        payload.get("artifact_schema"),
        artifact.get("artifact_schema_version"),
        artifact.get("schema_version"),
    ]
    for value in candidates:
        if isinstance(value, str) and value:
            return value[:80]
    if artifact_available:
        # The public sync envelope exposes lineage availability but not the
        # artifact's top-level version.  Infer the current compatible
        # namespace so sync/artifact/recovery entries remain equivalent;
        # legacy artifacts without a version are intentionally treated as
        # compatible with that namespace.
        if payload.get("action_execution_id") or isinstance(
            result.get("action"), Mapping
        ):
            return "spatial-agent.action-artifact.v1"
        return RUN_ARTIFACT_SCHEMA_VERSION
    return None


def _artifact_available(
    payload: Mapping[str, Any],
    *,
    result: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> bool:
    """Project artifact existence as a boolean without comparing its path."""
    explicit = payload.get("artifact_available")
    if isinstance(explicit, bool):
        return explicit

    for value in (
        artifact.get("available"),
        _mapping(payload.get("artifact")).get("available"),
    ):
        if isinstance(value, bool):
            return value

    lineage_artifact = _mapping(_mapping(result.get("lineage")).get("artifact"))
    if isinstance(lineage_artifact.get("available"), bool):
        return lineage_artifact["available"]

    if isinstance(payload.get("artifact_schema_version"), str):
        return bool(payload["artifact_schema_version"])
    if isinstance(payload.get("artifact_ref"), str):
        return bool(payload["artifact_ref"])
    return False


def _async_result_evidence_projection(
    payload: Mapping[str, Any],
) -> Dict[str, Any] | None:
    """Keep the cross-entry portion of async result evidence only.

    Async observations also carry request fingerprints, run identifiers and
    timing data.  Those fields are useful operationally but are not part of
    a sync/HTTP/artifact equivalence contract, so this projection deliberately
    excludes them.
    """
    observation = payload.get("async_observability")
    observation = observation if isinstance(observation, Mapping) else None
    evidence = observation.get("result_evidence") if observation else None
    if not isinstance(evidence, Mapping):
        evidence = payload.get("result_evidence")
    # Run artifacts persist the same bounded projection at the top level so
    # artifact-only recovery does not need to recreate the full async
    # observation envelope.  Treat that durable location as equivalent to
    # the live polling locations above.
    if not isinstance(evidence, Mapping):
        evidence = payload.get("async_result_evidence")
    if not isinstance(evidence, Mapping):
        return None

    evidence_artifact = _mapping(evidence.get("artifact"))
    evidence_views = _mapping(evidence.get("views"))
    evidence_planning = _mapping(evidence.get("planning"))
    evidence_projection = project_evidence_projection(evidence)
    evidence_selection = _mapping(evidence_projection.get("selection"))
    return {
        "schema_version": _stable_version(evidence.get("schema_version")),
        "state": _stable_status(evidence.get("state")),
        "status": _stable_status(evidence.get("status")),
        "request_identity": normalize_request_identity(
            evidence.get("request_identity")
        ),
        "plan_identity": normalize_plan_identity(
            evidence_planning.get("plan_identity")
        ),
        "degradation_status": _stable_status(
            evidence.get("degradation_status")
        ),
        "lifecycle": _lifecycle_projection(
            {"status": evidence.get("status"), "lifecycle": evidence.get("lifecycle")}
        ),
        "artifact_available": _optional_bool(evidence_artifact.get("available")),
        "views": _view_state_projection(evidence_views),
        "plan_quality": project_plan_quality_evidence(
            evidence_planning.get("plan_quality")
        ),
        "workflow_selection": normalize_workflow_selection_evidence(
            evidence_selection.get("workflow_selection")
        ),
        "planner_selection": normalize_planner_selection_evidence(
            evidence_selection.get("planner_selection")
        ),
        "selection_interaction": _selection_interaction_projection(
            evidence.get("selection_interaction")
        ),
        "action_receipt_identity_linkage": normalize_action_receipt_identity_linkage(
            evidence
        ).as_dict(),
        "execution_timeline": normalize_execution_timeline(
            evidence.get("execution_timeline"),
            include_action_events=False,
        ),
        "evidence_registry": normalize_evidence_registry(
            evidence_projection.get("evidence_registry")
        ),
        "evidence_registry_completeness": project_evidence_registry_completeness(
            evidence_projection.get("evidence_registry")
        ),
        "evidence_projection": evidence_projection,
    }


def _selection_interaction_projection(value: Any) -> Dict[str, Any]:
    """Compare selection interaction without volatile subject identities.

    The public interaction projection may carry a run id and a decision id so
    a transport can submit the next action. Those identities are not part of
    cross-entry equivalence: the stable contract is the state, reason, action
    allowlist, selection facts, missing facts, lifecycle summary, and bounded
    decision status/version.
    """
    interaction = normalize_selection_interaction(value)
    decision = _mapping(interaction.get("decision"))
    return {
        "schema_version": _stable_version(interaction.get("schema_version")),
        "available": bool(interaction.get("available")),
        "state": _stable_status(interaction.get("state")),
        "reason_code": _stable_status(interaction.get("reason_code")),
        "status": _stable_status(interaction.get("status")),
        "allowed_actions": [
            str(item)[:32]
            for item in (interaction.get("allowed_actions") or [])[:8]
        ],
        "selection": interaction.get("selection")
        if isinstance(interaction.get("selection"), Mapping)
        else {},
        "missing_fields": interaction.get("missing_fields")
        if isinstance(interaction.get("missing_fields"), list)
        else [],
        "lifecycle": interaction.get("lifecycle")
        if isinstance(interaction.get("lifecycle"), Mapping)
        else {},
        "decision": {
            "status": _stable_status(decision.get("status")),
            "version": decision.get("version")
            if isinstance(decision.get("version"), int)
            else None,
            "options": [
                str(item)[:32]
                for item in (decision.get("options") or [])[:8]
            ],
        }
        if decision
        else None,
    }


def _degradation_and_view_states(
    payload: Mapping[str, Any],
    *,
    result: Mapping[str, Any],
    views: Mapping[str, Any],
) -> Dict[str, Any]:
    """Project durable degradation and view state without volatile detail."""
    degradation = result.get("degradation")
    if not isinstance(degradation, Mapping):
        degradation = payload.get("degradation")
    degradation = degradation if isinstance(degradation, Mapping) else {}
    items = degradation.get("items")
    if not isinstance(items, list):
        items = _mapping(result.get("data")).get("degradations")
    codes = sorted(
        {
            str(item.get("code"))[:96]
            for item in (items if isinstance(items, list) else [])
            if isinstance(item, Mapping) and item.get("code")
        }
    )
    return {
        "degradation": {
            "schema_version": _stable_version(degradation.get("schema_version")),
            "status": _stable_status(degradation.get("status")),
            "codes": codes,
        },
        "views": _view_state_projection(views),
    }


def _view_state_projection(views: Mapping[str, Any]) -> Dict[str, Any]:
    """Project view schema and panel kind/state, omitting display payloads."""
    panels = views.get("panels") if isinstance(views, Mapping) else None
    panels = panels if isinstance(panels, Mapping) else {}
    projected: Dict[str, Any] = {}
    for panel_id, panel in sorted(panels.items(), key=lambda item: str(item[0])):
        if not isinstance(panel, Mapping):
            continue
        kind = _stable_status(panel.get("kind"))
        state = panel.get("state")
        if not isinstance(state, str) or not state:
            state = "unavailable" if kind == "unavailable" else "available"
        projected[str(panel_id)] = {
            "kind": kind,
            "state": _stable_status(state),
            "artifact_available": _optional_bool(panel.get("artifact_available")),
        }
    return {
        "schema_version": _stable_version(
            views.get("schema_version") if isinstance(views, Mapping) else None
        ),
        "panels": projected,
    }


def _stable_version(value: Any) -> str | None:
    return value[:80] if isinstance(value, str) and value else None


def _stable_status(value: Any) -> str | None:
    return value[:96] if isinstance(value, str) and value else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def normalize_execution(payload: Mapping[str, Any]) -> Dict[str, Any] | None:
    """Project Run/Action execution identity without volatile ids or timing."""
    record = payload.get("execution_record")
    if not isinstance(record, Mapping):
        if not payload.get("run_id") and not payload.get("action_execution_id"):
            # Legacy contract fixtures may represent only the result envelope.
            # Preserve that transport contract instead of inventing an identity.
            return None
        record = build_execution_record(payload)
    return execution_record_summary(record)


def compare_results(
    payloads: Sequence[Mapping[str, Any]],
) -> List[str]:
    """Return bounded differences across two or more public result payloads."""

    if len(payloads) < 2:
        raise ValueError("at least two result payloads are required")
    contracts = [normalize_result(payload) for payload in payloads]
    # Async evidence is an optional transport projection. A synchronous
    # entry cannot produce it, so comparing it against a polling/artifact
    # entry would report a false drift in the shared core contract. When all
    # entries carry the projection it remains strictly comparable, including
    # its version/state changes.
    if any(contract.values.get("async_result_evidence") is None for contract in contracts):
        contracts = [
            CrossEntryContract(
                {
                    key: value
                    for key, value in contract.values.items()
                    if key != "async_result_evidence"
                }
            )
            for contract in contracts
        ]
    baseline = contracts[0]
    differences: List[str] = []
    for index, contract in enumerate(contracts[1:], start=1):
        for path in baseline.differences(contract):
            differences.append(f"entry[0] vs entry[{index}]: {path}")
    return differences[:100]


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _differences(left: Any, right: Any, path: str = "$") -> List[str]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        differences: List[str] = []
        for key in sorted(set(left) | set(right), key=str):
            child = f"{path}.{key}"
            if key not in left or key not in right:
                differences.append(child)
            else:
                differences.extend(_differences(left[key], right[key], child))
        return differences
    if isinstance(left, list) and isinstance(right, list):
        differences = []
        if len(left) != len(right):
            differences.append(f"{path}.length")
        for index, (left_value, right_value) in enumerate(zip(left, right)):
            differences.extend(_differences(left_value, right_value, f"{path}[{index}]"))
        return differences
    return [] if left == right else [path]
