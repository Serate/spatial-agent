/* Canonical interaction.v1 consumer shared by every Console journey. */
(function attachConsoleInteraction(root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ConsoleInteraction = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function createModule() {
  const VERSION = "spatial-agent.interaction.v1";
  const COMMAND_VERSION = "spatial-agent.interaction-command.v1";
  const ACTION_VERSION = "spatial-agent.interaction-action.v1";
  const STATES = new Set([
    "candidate_selection", "facts_required", "confirmation_required",
    "repairable", "recoverable", "processing", "completed", "rejected",
    "cancelled", "failed", "unavailable",
  ]);
  const record = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
  const text = (value, fallback = "", limit = 160) => {
    const result = (typeof value === "string" || typeof value === "number")
      ? String(value).replace(/[\u0000-\u001f\u007f]/g, " ").trim()
      : "";
    return (result || fallback).slice(0, limit);
  };

  function source(data) {
    if (!record(data)) return null;
    if (data.schema_version === VERSION) return data;
    if (record(data.interaction)) return data.interaction;
    return record(data.result) && record(data.result.interaction) ? data.result.interaction : null;
  }

  function subjectRef(value) {
    if (!record(value)) return {kind: "unknown", id: "unknown"};
    return {kind: text(value.kind, "unknown", 32), id: text(value.id, "unknown", 160)};
  }

  function normalize(data) {
    const raw = source(data);
    if (!record(raw) || raw.schema_version !== VERSION) return unavailable(raw?.schema_version ? "interaction_unknown_schema" : "interaction_missing");
    const subject = record(raw.subject) ? raw.subject : {};
    const state = STATES.has(raw.state) ? raw.state : "unavailable";
    const actions = (Array.isArray(raw.actions) ? raw.actions : []).slice(0, 12).map(item => {
      if (!record(item) || item.schema_version !== ACTION_VERSION || !text(item.id)) return null;
      return {
        schema_version: ACTION_VERSION,
        id: text(item.id, "", 48),
        kind: text(item.kind, "interaction", 32),
        label: text(item.label, item.id, 80),
        description: text(item.description, "", 320),
        input_schema: record(item.input_schema) ? item.input_schema : {type: "object", properties: {}, required: [], additionalProperties: false},
        idempotency_required: item.idempotency_required !== false,
      };
    }).filter(Boolean);
    const revision = Number.isInteger(subject.revision) && subject.revision >= 0 ? subject.revision : 0;
    const available = raw.available === true && state !== "unavailable";
    return {
      schema_version: VERSION,
      available,
      actionable: available && raw.actionable === true && actions.length > 0,
      subject: {
        root: subjectRef(subject.root),
        current: subjectRef(subject.current),
        revision,
        domain_id: text(subject.domain_id, "", 80),
      },
      kind: text(raw.kind, "unavailable", 64),
      state,
      phase: text(raw.phase, "unknown", 32),
      status: text(raw.status, "UNKNOWN", 32),
      reason_code: text(raw.reason_code, "interaction_unavailable", 96),
      actions: available ? actions : [],
      blocked_actions: (Array.isArray(raw.blocked_actions) ? raw.blocked_actions : []).slice(0, 12).map(value => text(record(value) ? value.id : value, "", 48)).filter(Boolean),
      content: record(raw.content) ? raw.content : {},
      receipt: record(raw.receipt) ? raw.receipt : null,
      lineage: record(raw.lineage) ? raw.lineage : {},
    };
  }

  function command(model, actionId, input, idempotencyKey) {
    const normalized = normalize(model);
    const action = normalized.actions.find(item => item.id === actionId);
    if (!normalized.actionable || !action) throw new Error("该动作已不在当前交互授权列表中，请刷新后重试。");
    const key = text(idempotencyKey, "", 128);
    if (!key || /[\\/]/.test(key)) throw new Error("动作缺少有效幂等键。");
    return {
      schema_version: COMMAND_VERSION,
      subject: normalized.subject,
      action_id: action.id,
      input: record(input) ? input : {},
      idempotency_key: key,
    };
  }

  function catalog(model) {
    const normalized = normalize(model);
    return {schema_version: "spatial-agent.actions.v1", actions: normalized.actions};
  }

  function candidates(model) {
    const normalized = normalize(model);
    return (Array.isArray(normalized.content.candidates) ? normalized.content.candidates : []).slice(0, 24).filter(record).map(item => ({
      id: text(item.id || item.capability_id || item.domain_id, "", 96),
      label: text(item.label || item.name || item.id || item.capability_id || item.domain_id, "候选项", 128),
      description: text(item.description, "", 320),
      capability_ids: (Array.isArray(item.capability_ids) ? item.capability_ids : []).slice(0, 12).map(value => text(value, "", 96)).filter(Boolean),
    }));
  }

  function unavailable(reason) {
    return {
      schema_version: VERSION, available: false, actionable: false,
      subject: {root: {kind: "unknown", id: "unknown"}, current: {kind: "unknown", id: "unknown"}, revision: 0, domain_id: ""},
      kind: "unavailable", state: "unavailable", phase: "unknown", status: "UNKNOWN",
      reason_code: reason, actions: [], blocked_actions: [], content: {}, receipt: null, lineage: {},
    };
  }

  return Object.freeze({VERSION, COMMAND_VERSION, ACTION_VERSION, normalize, command, catalog, candidates});
});
