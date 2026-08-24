/*
 * M150-C Console decision-evidence smoke.
 *
 * Node-only and intentionally offline: no HTTP, Docker, GIS, credentials,
 * live provider, browser, or CDP session is required.
 */
const assert = require("node:assert/strict");
const evidence = require("../web/src/console_decision_evidence.js");

const repairPayload = {
  status: "COMPLETED",
  result: {
    replanning: {
      schema_version: "spatial-agent.replanning.v1",
      available: true,
      count: 1,
      events: [{
        phase: "planning",
        failed_step_id: "plan-validation",
        failed_tool: "planner",
        failure_category: "tool_validation",
        replanned_step_ids: ["summary"],
        error: "provider raw error must not cross the Console seam",
      }],
    },
  },
};
const repaired = evidence.normalize(repairPayload);
assert.equal(repaired.repair.state, "available");
assert.equal(repaired.repair.count, 1);
assert.equal(repaired.repair.events[0].failed_step_id, "plan-validation");
assert.equal("error" in repaired.repair.events[0], false);
const repairedHtml = evidence.render(repairPayload).html;
assert.match(repairedHtml, /计划修复/);
assert.doesNotMatch(repairedHtml, /provider raw error/);

const evaluationPayload = {
  status: "COMPLETED",
  repair_evidence: {
    schema_version: "spatial-agent.repair-evaluation.v1",
    available: true,
    lineage: {
      events: [{
        phase: "execution",
        failed_step_id: "screening",
        failed_tool: "get_candidates",
        failure_category: "execution",
        replanned_step_ids: [],
      }],
    },
  },
};
assert.equal(evidence.normalize(evaluationPayload).repair.state, "available");

const unknown = evidence.render({
  status: "COMPLETED",
  repair_evidence: {
    schema_version: "spatial-agent.repair-evaluation.v99",
    lineage: {events: [{error: "secret provider response"}]},
  },
});
assert.equal(unknown.model.repair.state, "unavailable");
assert.match(unknown.html, /有界状态|未知版本/);
assert.doesNotMatch(unknown.html, /secret provider response/);

const rejected = evidence.render({
  status: "REJECTED",
  error: "raw rejection explanation must not render",
  failure: {schema_version: "spatial-agent.failure.v1", category: "policy", code: "request_rejected", phase: "planning"},
});
assert.equal(rejected.model.rejection.state, "rejected");
assert.match(rejected.html, /拒绝证据/);
assert.doesNotMatch(rejected.html, /raw rejection explanation/);

const clarification = evidence.render({
  status: "NEEDS_CLARIFICATION",
  error: "raw clarification error must not render",
  clarification: {
    schema_version: "spatial-agent.clarification.v1",
    state: "matched_capability_missing_parameters",
    missing: ["区域", "分析条件"],
    matched_capabilities: ["spatial_overview"],
    next_actions: ["补充区域与分析条件"],
  },
});
assert.equal(clarification.model.clarification.state, "needs_clarification");
assert.match(clarification.html, /澄清证据/);
assert.doesNotMatch(clarification.html, /raw clarification error/);

const missing = evidence.normalize({status: "COMPLETED"});
assert.equal(missing.repair.state, "missing");
assert.equal(missing.repair.count, 0);
assert.ok(evidence.render({status: "COMPLETED"}).html.length < 5000);

console.log(JSON.stringify({
  status: "ok",
  cases: ["replanning", "repair_evaluation", "unknown", "rejected", "clarification", "missing"],
  states: {
    available: repaired.repair.state,
    unknown: unknown.model.repair.state,
    missing: missing.repair.state,
  },
}));
