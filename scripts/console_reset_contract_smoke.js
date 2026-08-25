"use strict";

/* M284-D: concise offline contract for reset boundaries and stale renders. */
const assert = require("node:assert/strict");
const RendererRegistry = require("../web/src/console_renderer_registry.js");
const GisPlugin = require("../web/src/console_gis_plugin.js");

async function main() {
  const generic = {innerHTML: "旧的通用结果"};
  const visual = {innerHTML: "旧的地图结果", replaceChildren() { this.innerHTML = ""; }};
  const selection = {textContent: "已选中：洪山区"};
  const selectionButton = {disabled: false, dataset: {}, addEventListener() {}};
  const registry = RendererRegistry.create();
  const gis = GisPlugin.createMapAdapter({
    selectionTarget: selection,
    useSelectionButton: selectionButton,
  });
  registry.register("map", gis);

  await registry.renderWorkspace({
    panels: {map: {kind: "map", mode: "geojson", geojson: {type: "FeatureCollection", features: []}}},
    specs: [{id: "map", renderer: "map"}],
    surfaces: {generic, visual},
  });
  assert.match(selection.textContent, /可视化要素/);

  registry.reset({reason: "clear-session", generation: 7, surfaces: {generic, visual}});
  assert.equal(visual.innerHTML, "");
  assert.deepEqual(registry.context(), {});
  assert.equal(selectionButton.disabled, true);

  let release;
  registry.register("slow", {
    async render() {
      await new Promise(resolve => { release = resolve; });
      return {html: "不应回写的旧结果"};
    },
  });
  const stale = registry.renderWorkspace({
    panels: {slow: {kind: "slow"}},
    specs: [{id: "slow", renderer: "slow"}],
    surfaces: {generic, visual},
  });
  registry.reset({reason: "domain-change", surfaces: {generic, visual}});
  release();
  assert.equal((await stale).status, "superseded");
  assert.doesNotMatch(generic.innerHTML, /不应回写的旧结果/);

  console.log(JSON.stringify({ok: true, reset: "passed", stale_render: "superseded"}));
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
