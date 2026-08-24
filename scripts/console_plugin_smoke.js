"use strict";

const assert = require("node:assert/strict");
const RendererRegistry = require("../web/console_renderer_registry.js");
const ActionHost = require("../web/console_action_host.js");
const GisPlugin = require("../web/console_gis_plugin.js");

async function main() {
  const generic = {innerHTML: ""};
  const visual = {innerHTML: ""};
  const selection = {textContent: ""};
  const selectionButton = {disabled: false, dataset: {}, addEventListener() {}};
  const registry = RendererRegistry.create();
  registry.register("map", GisPlugin.createMapAdapter({
    selectionTarget: selection,
    useSelectionButton: selectionButton,
  }));

  const report = await registry.renderWorkspace({
    panels: {
      summary: {kind: "metrics", title: "通用结果", metrics: [{label: "数量", value: 1}]},
      preview: {
        kind: "map",
        mode: "geojson",
        geojson: {
          type: "FeatureCollection",
          features: [{
            type: "Feature",
            properties: {name: "fixture"},
            geometry: {type: "Polygon", coordinates: [[[114.3, 30.4], [114.4, 30.4], [114.4, 30.5], [114.3, 30.4]]]},
          }],
        },
      },
    },
    specs: [
      {id: "summary", renderer: "metrics"},
      {id: "preview", renderer: "map"},
    ],
    surfaces: {generic, visual},
  });
  assert.equal(report.status, "rendered");
  assert.deepEqual(new Set(report.rendered_surfaces), new Set(["generic", "visual"]));
  assert.match(generic.innerHTML, /通用结果/);
  assert.match(visual.innerHTML, /<svg/);

  const boundsTarget = {innerHTML: ""};
  await GisPlugin.createMapAdapter().render({
    target: boundsTarget,
    view: {mode: "raster_bounds", bounds: [0, 0, 10, 5], dataset: "dem", crs: "EPSG:4326"},
    isCurrent: () => true,
  });
  assert.match(boundsTarget.innerHTML, /栅格外接范围/);
  assert.doesNotMatch(boundsTarget.innerHTML, /fill-opacity="\.48"/);

  registry.register("broken", {surface: "visual", render() { throw new Error("fixture"); }});
  const degraded = await registry.renderWorkspace({
    panels: {broken: {kind: "broken", title: "故障 adapter"}},
    specs: [{id: "broken", renderer: "broken", title: "故障 adapter"}],
    surfaces: {generic, visual},
  });
  assert.equal(degraded.status, "degraded");
  assert.equal(degraded.failures.length, 1);
  assert.match(generic.innerHTML, /故障 adapter/);

  let releaseSlow;
  registry.register("slow", {
    async render() { await new Promise(resolve => { releaseSlow = resolve; }); return {html: "stale"}; },
  });
  const staleRender = registry.renderWorkspace({
    panels: {slow: {kind: "slow"}},
    specs: [{id: "slow", renderer: "slow"}],
    surfaces: {generic, visual},
  });
  const currentRender = await registry.renderWorkspace({
    panels: {current: {kind: "metrics", title: "当前结果", metrics: []}},
    specs: [{id: "current", renderer: "metrics"}],
    surfaces: {generic, visual},
  });
  releaseSlow();
  assert.equal((await staleRender).status, "superseded");
  assert.equal(currentRender.status, "rendered");
  assert.doesNotMatch(generic.innerHTML, /stale/);

  const fields = [
    {dataset: {actionField: "limit", actionType: "integer"}, value: "20"},
    {dataset: {actionField: "names", actionType: "array", itemType: "string"}, value: "甲,乙"},
  ];
  const payload = ActionHost.collectPayload(
    {querySelectorAll: () => fields},
    {
      type: "object",
      required: ["limit", "names"],
      properties: {
        limit: {type: "integer", minimum: 1, maximum: 100},
        names: {type: "array", minItems: 2, items: {type: "string"}},
      },
    },
  );
  assert.deepEqual(payload, {limit: 20, names: ["甲", "乙"]});

  registry.reset({surfaces: {generic, visual}});
  assert.deepEqual(registry.context(), {});
  assert.equal(selectionButton.disabled, true);
  console.log(JSON.stringify({renderer: report.status, degraded: degraded.status, action_payload: payload, reset: "passed"}));
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
