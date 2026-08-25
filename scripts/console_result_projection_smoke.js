/* M283-D Node smoke for the domain-neutral user-facing result projection. */
const assert = require("node:assert/strict");
const projection = require("../web/src/console_result_projection.js");

const completed = projection.normalize({
  status: "COMPLETED",
  runtime_context: {schema_version: "spatial-agent.composite-request-context.v2", domain_id: "gis", fingerprint: "secret-context-is-not-rendered"},
  plan: {steps: [{id: "one", tool: "private_tool"}]},
  plan_evidence: {source: "replay", step_count: 1},
  result: {
    type: "composite_result",
    data_profile: {primary: "composite", kinds: ["composite", "metrics"]},
    view: {
      schema_version: "spatial-agent.composite-view.v1",
      answer: {headline: "分析完成", summary: "已形成一份可读的综合结论。", key_findings: ["发现一", "发现二"], limitations: ["仅供演示"]},
      sections: [{kind: "component", answer: "组件结果"}],
      views: [{view_id: "summary", kind: "metrics", state: "ready", payload: {metrics: []}}],
      evidence: {available: true, component_count: 1},
      planning: {
        schema_version: "spatial-agent.composite-planner-evidence.v1",
        planner_source: "llm",
        structured_output: {
          schema_version: "spatial-agent.provider-structured-output.v1",
          wire_api: "chat_completions",
          structured_mode: "json_schema",
          schema_enforced: true,
          source: "config",
          reason_code: "configured",
          status: "success",
        },
      },
      artifacts: [{available: true, kind: "run", ref: "run.json"}],
    },
  },
});
assert.equal(completed.answer.summary, "已形成一份可读的综合结论。");
assert.equal(completed.view_count, 1);
assert.equal(completed.phases.filter(item => item.state === "complete").length, 5);
assert.equal(completed.phases[1].state, "not_needed");
assert.equal(completed.planning.structured_output.structured_mode, "json_schema");
const completedHtml = projection.render(completed);
assert.match(completedHtml, /关键发现/);
assert.match(completedHtml, /分析上下文已建立/);
assert.match(completedHtml, /计划格式已确认/);
assert.doesNotMatch(completedHtml, /secret-context-is-not-rendered/);
assert.doesNotMatch(completedHtml, /private_tool/);

const clarification = projection.normalize({
  status: "NEEDS_CLARIFICATION",
  clarification: {state: "needs_clarification", missing: ["时间范围", "指标"], next_actions: ["请补充统计周期"]},
  result: {type: "unknown"},
});
assert.equal(clarification.phases[1].state, "active");
const clarificationHtml = projection.render(clarification);
assert.match(clarificationHtml, /需要补充的信息/);
assert.match(clarificationHtml, /时间范围/);
assert.match(clarificationHtml, /请补充统计周期/);
assert.ok(clarificationHtml.length < 12000);

const repaired = projection.normalize({
  status: "PLANNED",
  repair_lineage: {
    schema_version: "spatial-agent.planner-repair-lineage.v1",
    status: "repaired",
    attempted: true,
    count: 1,
    reason_code: "plan_component_field_invalid",
  },
  result: {type: "composite_result"},
});
assert.equal(repaired.repair_lineage.status, "repaired");
assert.match(projection.render(repaired), /计划已校正/);

console.log(JSON.stringify({status: "ok", cases: ["completed_projection", "clarification_projection", "repair_projection"]}));
