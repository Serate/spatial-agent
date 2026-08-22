const interaction = require("../web/console_selection_interaction.js");

const model = interaction.normalize({
  schema_version: interaction.VERSION,
  available: true,
  state: "candidate_selection",
  reason_code: "selection_requires_user_choice",
  status: "NEEDS_CLARIFICATION",
  allowed_actions: ["select_capability", "select_workflow", "unknown"],
  blocked_actions: ["repair"],
  action_preconditions: {
    schema_version: "spatial-agent.action-precondition.v1",
    available: true,
    state: "blocked",
    action_allowed: false,
    enforcement: "enforced",
    reason_code: "action_preconditions_blocked",
    condition_count: 1,
    conditions: [{id: "alignment", status: "blocked", blocking: true}],
  },
  action_receipt: {
    schema_version: "spatial-agent.action-receipt.v1",
    action_id: "repair",
    status: "FAILED",
    reused: true,
  },
  repair_lineage: [{phase: "planning", repair_status: "repaired", repair_reason_code: "replacement_selected"}],
  selection: {
    state: "ambiguous",
    candidate_ids: ["capability_a", "capability_b"],
  },
  evidence_action_guidance: {
    schema_version: interaction.GUIDANCE_VERSION,
    available: true,
    state: "degraded",
    reason_code: "selection_requires_facts",
    recommended_actions: ["provide_facts", "repair", "unknown"],
    missing_fields: [{id: "region", label: "区域", kind: "entity"}],
    source: "domain",
  },
  missing_fields: [],
});

if (model.state !== "candidate_selection") throw new Error("state normalization failed");
if (model.allowed_actions.join(",") !== "select_capability,select_workflow") {
  throw new Error("action allowlist failed");
}
if (interaction.normalize({schema_version: "future.v9"}).state !== "unavailable") {
  throw new Error("future schema fallback failed");
}
if (model.evidence_action_guidance.recommended_actions.join(",") !== "provide_facts,repair,unknown") {
  throw new Error("guidance projection failed");
}
if (model.evidence_action_guidance.missing_fields[0].id !== "region") {
  throw new Error("guidance facts projection failed");
}
if (model.blocked_actions.join(",") !== "repair" || model.action_preconditions.state !== "blocked") {
  throw new Error("precondition projection failed");
}
if (model.action_receipt?.action_id !== "repair" || model.repair_lineage.length !== 1) {
  throw new Error("receipt/repair lineage projection failed");
}

process.stdout.write(JSON.stringify({status: "ok", state: model.state, actions: model.allowed_actions, guidance: model.evidence_action_guidance.state}));
