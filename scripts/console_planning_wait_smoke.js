"use strict";

// Regression smoke for a slow provider during planning.  It checks the
// user-facing action text without calling a model or exposing provider text.
const fs = require("fs");
const assert = require("assert");

function extractFunction(source, name) {
  const start = source.indexOf("function " + name);
  assert(start >= 0, name + " must be present");
  const opening = source.indexOf("{", start);
  let depth = 0;
  for (let index = opening; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(start, index + 1);
  }
  throw new Error(name + " is not balanced");
}

const source = fs.readFileSync("web/src/console_app.js", "utf8");
const elements = new Map([
  ["liveRunPhase", {}],
  ["liveRunDuration", {}],
  ["liveRunAction", {}],
  ["liveRunHeartbeat", {}],
  ["liveSummaryMeta", {}],
  ["liveProgressFill", {style: {}}],
]);
const liveRunState = {
  currentPhase: "plan",
  currentAction: "正在生成任务计划。",
  startedAt: Date.now() - 20_000,
  lastEventAt: Date.now() - 2_000,
  transport: "sse",
  eventCount: 5,
};
const refreshLiveSummary = new Function(
  "liveRunState",
  "$",
  "liveDurationText",
  "liveHeartbeatText",
  "window",
  "return (" + extractFunction(source, "refreshLiveSummary") + ");",
)(
  liveRunState,
  id => elements.get(id),
  () => "20 秒",
  () => "2 秒前",
  {ConsoleRunEvents: {phaseLabel: () => "生成计划"}},
);

refreshLiveSummary();
assert.match(
  elements.get("liveRunAction").textContent || "",
  /响应较慢|等待.*模型|已耗时/,
  "a slow planning request must not look frozen",
);
console.log("console planning wait smoke: ok");
