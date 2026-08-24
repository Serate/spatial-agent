/*
 * M149 Console contract smoke.
 *
 * This is intentionally a Node-only check.  It exercises the same bounded
 * normalization module loaded by web/index.html without HTTP, Docker, GIS,
 * credentials, or a browser/CDP session.
 */
const assert = require("node:assert/strict");
const schema = require("../web/console_nested_schema.js");

const valid = schema.normalize({
  result: {
    schema_version: "spatial-agent.result-envelope.v1",
    type: "text_summary_result",
    data_profile: {
      schema_version: "spatial-agent.data-profile.v1",
      primary: "text",
      kinds: ["text", "document_evidence"],
    },
    workspace: {
      schema_version: "spatial-agent.workspace.v1",
      panels: ["generic"],
      view_specs: [{
        id: "generic",
        renderer: "generic",
        title: "摘要",
        schema_version: "spatial-agent.view.v1",
      }],
    },
    views: {
      schema_version: "spatial-agent.views.v1",
      panels: {
        generic: {
          schema_version: "spatial-agent.view.v1",
          kind: "text_summary",
          rows: [{label: "结论", value: "已完成"}],
        },
      },
    },
  },
});
assert.equal(valid.invalid, false);
assert.equal(valid.result.views.panels.generic.kind, "text_summary");
assert.equal(valid.result.data_profile.primary, "text");

const legacy = schema.normalize({
  result_type: "legacy_result",
  result: {
    type: "legacy_result",
    workspace: {panels: ["generic"], view_specs: [{id: "generic"}]},
    views: {panels: {generic: {kind: "summary"}}},
  },
});
assert.equal(legacy.invalid, false, "missing nested versions remain legacy-compatible");
assert.equal(legacy.result.views.panels.generic.schema_version, "spatial-agent.view.v1");
assert.equal(legacy.result.data_profile.primary, "unknown");

const unknownWorkspace = schema.normalize({
  artifact_ref: "safe-run.json",
  result: {
    schema_version: "spatial-agent.result-envelope.v1",
    type: "future_result",
    workspace: {schema_version: "spatial-agent.workspace.v9", panels: ["future"]},
    views: {schema_version: "spatial-agent.views.v1", panels: {}},
  },
});
assert.equal(unknownWorkspace.invalid, true);
assert.deepEqual(unknownWorkspace.workspace.panels, ["generic"]);
assert.equal(unknownWorkspace.views.panels.generic.kind, "unavailable");
assert.ok(unknownWorkspace.reason.length <= 320);

const unknownPanel = schema.normalize({
  result: {
    schema_version: "spatial-agent.result-envelope.v1",
    type: "custom_result",
    workspace: {schema_version: "spatial-agent.workspace.v1", panels: ["insights"]},
    views: {
      schema_version: "spatial-agent.views.v1",
      panels: {
        insights: {schema_version: "spatial-agent.view.v9", kind: "metrics"},
      },
    },
  },
});
assert.equal(unknownPanel.invalid, false, "one bad panel should not erase valid sibling views");
assert.equal(unknownPanel.hasUnavailablePanel, true);
assert.equal(unknownPanel.views.panels.insights.kind, "unavailable");
assert.equal(unknownPanel.views.panels.generic.kind, "unavailable");
assert.ok(unknownPanel.views.panels.insights.reason.length <= 320);

const malformed = schema.normalize({
  result: {
    schema_version: "spatial-agent.result-envelope.v1",
    type: "malformed_result",
    workspace: {schema_version: "spatial-agent.workspace.v1", panels: "generic"},
    views: {schema_version: "spatial-agent.views.v1", panels: null},
  },
});
assert.equal(malformed.invalid, true);
assert.equal(malformed.result.views.panels.generic.kind, "unavailable");
assert.ok(JSON.stringify(malformed.result).length < 4000, "fallback must remain bounded");

console.log(JSON.stringify({
  status: "ok",
  cases: ["current", "legacy", "unknown_workspace", "unknown_panel", "malformed"],
  fallback_kind: unknownWorkspace.views.panels.generic.kind,
}));
