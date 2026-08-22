/*
 * Domain-neutral Console seam for workflow-selection interaction.
 *
 * This module only normalizes the bounded server projection. It does not
 * choose a workflow, call an endpoint, or know GIS concepts; the main Console
 * decides how an allowed action is connected to its existing controls.
 */
(function attachConsoleSelectionInteraction(root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ConsoleSelectionInteraction = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function createConsoleSelectionInteraction() {
  const VERSION = "spatial-agent.selection-interaction.v1";
  const GUIDANCE_VERSION = "spatial-agent.evidence-action-guidance.v1";
  const STATES = new Set([
    "candidate_selection", "facts_required", "confirmation_required",
    "recoverable", "processing", "completed", "unavailable",
  ]);
  const ACTIONS = new Set([
    "select_capability", "select_workflow", "provide_facts", "preview",
    "confirm", "reject", "retry", "recover", "cancel",
  ]);
  const LIMIT = 16;

  function record(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function text(value, fallback = "", limit = 128) {
    const result = (typeof value === "string" || typeof value === "number")
      ? String(value).replace(/[\u0000-\u001f\u007f]/g, " ").trim()
      : "";
    return (result || fallback).slice(0, limit);
  }

  function list(value, mapper, limit = LIMIT) {
    return Array.isArray(value) ? value.slice(0, limit).map(mapper).filter(Boolean) : [];
  }

  function normalizeGuidance(value) {
    const source = record(value) ? value : {};
    if (source.schema_version !== GUIDANCE_VERSION) {
      return {
        schema_version: GUIDANCE_VERSION,
        available: false,
        state: "unavailable",
        reason_code: source.schema_version
          ? "evidence_action_guidance_unknown_schema"
          : "evidence_action_guidance_missing",
        recommended_actions: [],
        missing_fields: [],
        source: "none",
      };
    }
    return {
      schema_version: GUIDANCE_VERSION,
      available: source.available === true,
      state: text(source.state, "unknown", 32),
      reason_code: text(source.reason_code, "evidence_action_guidance_unavailable", 96),
      recommended_actions: list(source.recommended_actions, value => text(value, "", 48), 8),
      missing_fields: inputFacts(source.missing_fields),
      source: text(source.source, "unknown", 48),
    };
  }

  function inputFacts(value) {
    return list(value, item => {
      if (!record(item)) return null;
      const id = text(item.id, "", 96);
      return id ? {id, label: text(item.label, id, 128), kind: text(item.kind, "fact", 32)} : null;
    });
  }

  function candidateDetails(value) {
    return list(value, item => {
      if (!record(item)) return null;
      const id = text(item.id || item.capability_id, "", 96);
      if (!id) return null;
      const workflow = record(item.workflow) && text(item.workflow.template_id, "", 96)
        ? {
          template_id: text(item.workflow.template_id, "", 96),
          template_version: text(item.workflow.template_version, "1.0.0", 32),
          result_types: list(item.workflow.result_types, value => text(value, "", 96), 8),
          max_steps: Number.isInteger(item.workflow.max_steps) ? item.workflow.max_steps : null,
        }
        : null;
      const data = record(item.data) ? {
        dataset_gate: text(item.data.dataset_gate, "unknown", 24),
        capability_status: text(item.data.capability_status, "unknown", 24),
        missing_datasets: list(item.data.missing_datasets, value => text(value, "", 96), 8),
        geometry: text(item.data.geometry, "unknown", 96),
      } : {};
      const evidence = record(item.evidence) ? {
        schema_version: text(item.evidence.schema_version, "spatial-agent.capability-evidence.v1", 96),
        status: text(item.evidence.status, "unknown", 24),
        availability_mode: text(item.evidence.availability?.mode, "unknown", 24),
        availability_reason: text(item.evidence.availability?.reason, "unknown", 96),
        readiness: text(item.evidence.readiness?.status, "unknown", 24),
        alignment: text(item.evidence.alignment?.status, "unknown", 24),
        provenance: text(item.evidence.provenance?.status, "unknown", 24),
        missing_reasons: list(item.evidence.missing_reasons, value => text(value, "", 160), 8),
      } : null;
      const guidance = normalizeGuidance(item.evidence_action_guidance);
      return {
        id,
        label: text(item.label, id, 128),
        description: text(item.description, "", 320),
        available: item.available !== false,
        input_facts: inputFacts(item.input_facts),
        result_types: list(item.result_types, value => text(value, "", 96), 8),
        data,
        evidence,
        evidence_action_guidance: guidance,
        actions: list(item.actions, value => text(value, "", 32), 8),
        workflow,
      };
    });
  }

  function normalize(input) {
    const source = record(input) ? input : {};
    if (source.schema_version !== VERSION) {
      return {
        schema_version: VERSION,
        available: false,
        state: "unavailable",
        reason_code: source.schema_version ? "selection_interaction_unknown_schema" : "selection_interaction_missing",
        allowed_actions: [],
        selection: {state: "unavailable", candidate_ids: [], candidate_workflow_ids: [], missing_fields: []},
        missing_fields: [],
        evidence_action_guidance: normalizeGuidance(null),
      };
    }
    const selection = record(source.selection) ? source.selection : {};
    const state = STATES.has(source.state) ? source.state : "unavailable";
    const actions = list(source.allowed_actions, value => {
      const item = text(value, "", 40);
      return ACTIONS.has(item) ? item : "";
    }, 8);
    const missing = list(source.missing_fields, value => {
      if (!record(value)) return null;
      const id = text(value.id, "", 96);
      const label = text(value.label, id, 128);
      return id ? {id, label, kind: text(value.kind, "fact", 32)} : null;
    });
    return {
      schema_version: VERSION,
      available: source.available === true && state !== "unavailable",
      state,
      reason_code: text(source.reason_code, "selection_interaction_unavailable", 96),
      status: text(source.status, "UNKNOWN", 32),
      allowed_actions: actions,
      selection: {
        state: text(selection.state, "unavailable", 32),
        selected_capability_id: text(selection.selected_capability_id, "", 96),
        candidate_ids: list(selection.candidate_ids, value => text(value, "", 96)),
        candidate_workflow_ids: list(selection.candidate_workflow_ids, value => text(value, "", 96)),
        candidate_details: candidateDetails(selection.candidate_details),
        domain_seams: record(selection.domain_seams) ? selection.domain_seams : {},
      },
      missing_fields: missing,
      evidence_action_guidance: normalizeGuidance(
        source.evidence_action_guidance || selection.evidence_action_guidance
      ),
      decision: record(source.decision) ? {
        decision_id: text(source.decision.decision_id, "", 128),
        version: Number.isInteger(source.decision.version) ? source.decision.version : null,
        status: text(source.decision.status, "UNKNOWN", 32),
      } : null,
    };
  }

  return Object.freeze({VERSION, GUIDANCE_VERSION, STATES, ACTIONS, normalize, normalizeGuidance});
});
