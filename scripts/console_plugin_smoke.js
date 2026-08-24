"use strict";

const assert = require("node:assert/strict");
const RendererRegistry = require("../web/src/console_renderer_registry.js");
const ActionHost = require("../web/src/console_action_host.js");
const GisPlugin = require("../web/src/console_gis_plugin.js");

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

  const readable = {innerHTML: ""};
  await registry.renderWorkspace({
    panels: {
      stats: {
        kind: "raster_statistics",
        title: "高程统计",
        metrics: [
          {label: "最小值", value: 123.4567890123},
          {label: "最大值", value: 9876543210},
        ],
        distribution: {
          sample_count: 10000,
          bins: [
            {lower: 0, upper: 10, count: 7200},
            {lower: 10, upper: 20, count: 2800},
          ],
        },
        rows: [{label: "分布", value: {sample_count: 10000, bins: [{count: 7200}]}}],
      },
    },
    specs: [{id: "stats", renderer: "generic", title: "高程统计"}],
    surfaces: {generic: readable},
  });
  assert.match(readable.innerHTML, /123\.457/);
  assert.doesNotMatch(readable.innerHTML, /123\.4567890123/);
  assert.match(readable.innerHTML, /样本数量/);
  assert.match(readable.innerHTML, /区间分布/);
  assert.doesNotMatch(readable.innerHTML, /\[object Object\]/);

  const rasterElement = {addEventListener() {}};
  const rasterFitButton = {addEventListener() {}};
  const boundsMap = {
    bounds: null,
    fitBounds(value) { this.bounds = value; },
    invalidateSize() {},
    hasLayer() { return false; },
    remove() {},
  };
  const fakeLeaflet = {
    map() { return boundsMap; },
    rectangle(value) { return {value, addTo() { return this; }}; },
    tileLayer() { return {on() {}, addTo() { return this; }}; },
    layerGroup() { return {addTo() { return this; }}; },
    control: {
      scale() { return {addTo() {}}; },
      layers() { return {addTo() {}}; },
    },
  };
  const boundsTarget = {
    innerHTML: "",
    querySelector(selector) {
      if (selector === "[data-raster-map]") return rasterElement;
      if (selector === "[data-map-fit]") return rasterFitButton;
      return null;
    },
  };
  await GisPlugin.createMapAdapter({leaflet: fakeLeaflet}).render({
    target: boundsTarget,
    view: {mode: "raster_bounds", bounds: [114.3, 30.4, 114.4, 30.5], dataset: "dem", crs: "EPSG:4326"},
    isCurrent: () => true,
  });
  assert.match(boundsTarget.innerHTML, /data-raster-map/);
  assert.deepEqual(boundsMap.bounds, [[30.4, 114.3], [30.5, 114.4]]);
  assert.match(boundsTarget.innerHTML, /仅显示栅格外接范围/);

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
