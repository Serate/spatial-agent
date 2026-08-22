#!/usr/bin/env node

const assert = require("node:assert/strict");
const renderer = require("../web/console_workflow_evidence.js");

const composed = {
  status: "COMPLETED",
  plan: {
    steps: [
      {id: "boundary--filter", depends_on: []},
      {id: "dem--metadata", depends_on: ["boundary--filter"]},
    ],
  },
  plan_evidence: {
    workflow_selection: {
      state: "selected",
      workflow_components: [
        {
          component_id: "boundary",
          template_id: "admin_boundary_query",
          template_version: "1.0.0",
          depends_on_components: [],
          constraint_keys: ["admin_name"],
          evidence_keys: ["geometry"],
        },
        {
          component_id: "dem",
          template_id: "raster_metadata",
          template_version: "1.0.0",
          depends_on_components: ["boundary"],
          constraint_keys: ["dataset"],
          evidence_keys: ["metadata"],
        },
      ],
    },
  },
};

const model = renderer.normalize(composed);
assert.equal(model.available, true);
assert.equal(model.component_count, 2);
assert.equal(model.dependency_count, 1);
assert.equal(model.components[1].step_count, 1);

const html = renderer.render(composed);
assert.match(html, /workflow-component-card/);
assert.match(html, /admin_boundary_query/);
assert.match(html, /声明证据/);

assert.equal(renderer.render({}), "");
assert.equal(renderer.normalize({}).available, false);

console.log("console workflow evidence smoke passed");
