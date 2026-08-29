/* M324-C Node smoke for the safe tool-approval Console projection. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const projection = require("../web/src/console_tool_approvals.js");

const payload = {
  schema_version: "spatial-agent.tool-approval.v1",
  domain_id: "gis",
  visibility: [
    {
      schema_version: "spatial-agent.tool-approval-visibility.v1",
      approval_id: "approval-m324",
      name: "safe_metric",
      domain_id: "gis",
      status: "pending",
      version: 1,
      receipt_fingerprint: "sha256:approval-fingerprint",
      allowed_actions: ["approve", "reject", "not-a-real-action"],
      reason_code: "",
      recovery: {state: "not_loaded", reason_code: ""},
      definition: {source: "must not be rendered"},
    },
    {
      schema_version: "spatial-agent.tool-approval-visibility.v1",
      approval_id: "approval-bound",
      name: "bound_metric",
      domain_id: "gis",
      status: "approved",
      version: 2,
      receipt_fingerprint: "sha256:bound-fingerprint",
      allowed_actions: ["revoke"],
      reason_code: "approval_approved",
      recovery: {state: "bound", reason_code: "approval_binding_restored"},
    },
  ],
};
const model = projection.normalize(payload);
assert.equal(model.items.length, 2);
assert.deepEqual(model.items[0].allowed_actions, ["approve", "reject"]);
assert.equal(model.items[1].recovery.state, "bound");

const target = {innerHTML: "", querySelectorAll: () => []};
projection.mount({target, payload, escapeHtml: value => String(value).replace(/[&<>"']/g, "_")});
assert.match(target.innerHTML, /safe_metric/);
assert.match(target.innerHTML, /待审批/);
assert.match(target.innerHTML, /已恢复并绑定/);
assert.match(target.innerHTML, /批准/);
assert.match(target.innerHTML, /撤销/);
assert.doesNotMatch(target.innerHTML, /must not be rendered/);
assert.doesNotMatch(target.innerHTML, /definition/);
assert.match(fs.readFileSync("web/src/index.html", "utf8"), /console_tool_approvals\.js/);
console.log("console tool approvals smoke: ok");
