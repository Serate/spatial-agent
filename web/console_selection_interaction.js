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
      },
      missing_fields: missing,
      decision: record(source.decision) ? {
        decision_id: text(source.decision.decision_id, "", 128),
        version: Number.isInteger(source.decision.version) ? source.decision.version : null,
        status: text(source.decision.status, "UNKNOWN", 32),
      } : null,
    };
  }

  return Object.freeze({VERSION, STATES, ACTIONS, normalize});
});
