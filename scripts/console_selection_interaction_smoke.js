const interaction = require("../web/console_selection_interaction.js");

const model = interaction.normalize({
  schema_version: interaction.VERSION,
  available: true,
  state: "candidate_selection",
  reason_code: "selection_requires_user_choice",
  status: "NEEDS_CLARIFICATION",
  allowed_actions: ["select_capability", "select_workflow", "unknown"],
  selection: {
    state: "ambiguous",
    candidate_ids: ["capability_a", "capability_b"],
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

process.stdout.write(JSON.stringify({status: "ok", state: model.state, actions: model.allowed_actions}));
