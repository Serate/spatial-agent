/* M283-D Node smoke for the domain-neutral user-facing result projection. */
const assert = require("node:assert/strict");
const projection = require("../web/src/console_result_projection.js");

const completed = projection.normalize({
  status: "COMPLETED",
  runtime_context: {
    schema_version: "spatial-agent.composite-request-context.v2",
    domain_id: "gis",
    fingerprint: "secret-context-is-not-rendered",
    discovery: {
      schema_version: "spatial-agent.analysis-discovery.v1",
      state: "ready",
      reason_code: "discovery_ready",
      candidate_count: 2,
      data_requirement_count: 3,
      next_actions: ["由 Planner 组合已注册能力并生成计划"],
    },
  },
  plan: {steps: [{id: "one", tool: "private_tool"}]},
  plan_evidence: {
    source: "replay",
    step_count: 1,
    analysis_intents: [{
      domain_id: "gis",
      intent: {
        schema_version: "spatial-agent.analysis-intent.v1",
        operations: [{kind: "spatial_operation", output_kinds: ["vector"]}],
        data_kinds: ["vector"],
        source: "domain",
      },
    }],
    selection_evidence: {
      schema_version: "spatial-agent.selection-evidence.v1",
      state: "selected",
      selected_capability_keys: ["gis::summary"],
      candidates: [{selection_key: "gis::summary", label: "空间摘要", available: true, execution_ready: true}],
    },
  },
  result: {
    type: "composite_result",
    data_profile: {primary: "composite", kinds: ["composite", "metrics"]},
    result_summary: {
      schema_version: "spatial-agent.result-summary.v1",
      state: "complete",
      conclusion: "公共摘要已统一提供给所有入口。",
      key_findings: ["摘要不依赖 GIS 页面分支。"],
      evidence: {
        available: true,
        source_count: 1,
        sources: ["demo-source"],
        status: "ok",
        source_records: [{title: "官方统计公报", url: "https://www.gov.cn/report?id=1", domain: "www.gov.cn", snippet: "公开资料摘要"}],
      },
      blocks: [{
        block_id: "metrics",
        title: "指标结果",
        kind: "metrics",
        conclusion: "指标结果已整理。",
        facts: {count: 3, distribution: {bins: [{lower: 0, upper: 1, count: 2}]}},
        evidence: {
          available: true,
          source_count: 1,
          sources: ["demo-source"],
          status: "ok",
          source_records: [{title: "官方统计公报", url: "https://www.gov.cn/report?id=1", domain: "www.gov.cn", snippet: "公开资料摘要"}],
        },
      }],
    },
    view: {
      schema_version: "spatial-agent.composite-view.v1",
      answer: {headline: "分析完成", summary: "已形成一份可读的综合结论。", key_findings: ["发现一", "发现二"], limitations: ["仅供演示"]},
      sections: [{kind: "component", answer: "组件结果"}],
      views: [{view_id: "summary", kind: "metrics", state: "ready", payload: {metrics: []}}],
      evidence: {
        available: true,
        component_count: 1,
        answer_generation: {schema_version: "spatial-agent.answer-generation.v1", available: true, status: "success", mode: "live_model"},
      },
      planning: {
        schema_version: "spatial-agent.composite-planner-evidence.v1",
        planner_source: "llm",
        plan_completeness: {
          schema_version: "spatial-agent.plan-completeness.v1",
          status: "valid",
          reason_code: "plan_completeness_valid",
          component_count: 1,
          materialized_count: 1,
        },
        execution_binding: {
          schema_version: "spatial-agent.execution-binding.v1",
          binding_fingerprint: "sha256:binding-is-not-rendered",
        },
        structured_output: {
          schema_version: "spatial-agent.provider-structured-output.v1",
          wire_api: "chat_completions",
          structured_mode: "json_schema",
          schema_enforced: true,
          source: "config",
          reason_code: "configured",
          status: "success",
        },
        provider_runtime: {
          schema_version: "spatial-agent.provider-runtime.v1",
          health: {status: "configured", network: "not_checked", reason_code: "network_not_checked"},
          deadline: {state: "completed", deadline_exceeded: false, retryable: false},
        },
        planner_attempt: {
          schema_version: "spatial-agent.planner-attempt.v1",
          stage: "selection",
          state: "completed",
          outcome: "success",
          attempts: 1,
          retries: 0,
          retryable: false,
          next_actions: ["submit"],
          budget: {envelope_bytes: 18240, envelope_max_bytes: 96000},
        },
        canonical_plan: {
          schema_version: "spatial-agent.canonical-plan-receipt.v1",
          state: "executable",
          reason_code: "canonical_plan_validated",
          executable: true,
          component_count: 1,
          materialized_count: 1,
          component_ids: ["space"],
          request_fingerprint: "sha256:request",
          binding_fingerprint: "sha256:binding",
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
assert.equal(completed.planning.provider_runtime.deadline.state, "completed");
assert.equal(completed.planning.planner_attempt.outcome, "success");
assert.equal(completed.planning.planner_attempt.budget.envelope_bytes, 18240);
assert.deepEqual(completed.planning.planner_attempt.next_actions, ["submit"]);
assert.equal(completed.planning.canonical_plan.executable, true);
assert.equal(completed.analysis_intents.length, 1);
assert.equal(completed.analysis_intents[0].operations[0].kind, "spatial_operation");
assert.equal(completed.discovery.state, "ready");
assert.equal(completed.discovery.candidate_count, 2);
assert.equal(completed.selection_evidence.state, "selected");
assert.equal(completed.execution_binding.binding_fingerprint, "sha256:binding-is-not-rendered");
assert.equal(completed.answer_generation.status, "success");
assert.equal(completed.result_summary.conclusion, "公共摘要已统一提供给所有入口。");
assert.equal(completed.result_summary.blocks[0].kind, "metrics");
assert.equal(completed.result_summary.evidence.source_records[0].domain, "www.gov.cn");
const completedHtml = projection.render(completed);
assert.match(completedHtml, /关键发现/);
assert.match(completedHtml, /分析上下文已建立/);
assert.match(completedHtml, /计划格式已确认/);
assert.match(completedHtml, /计划已验证/);
assert.match(completedHtml, /执行链路已核验/);
assert.match(completedHtml, /能力与数据准备/);
assert.match(completedHtml, /能力与数据已发现/);
assert.match(completedHtml, /已选择：空间摘要/);
assert.match(completedHtml, /本次分析内容/);
assert.match(completedHtml, /空间关系/);
assert.match(completedHtml, /矢量/);
assert.match(completedHtml, /统一结果摘要/);
assert.match(completedHtml, /公共摘要已统一提供给所有入口/);
assert.match(completedHtml, /官方统计公报/);
assert.match(completedHtml, /https:\/\/www\.gov\.cn\/report\?id=1/);
assert.match(completedHtml, /结果明细/);
assert.doesNotMatch(completedHtml, /\[object Object\]/);
assert.doesNotMatch(completedHtml, /secret-context-is-not-rendered/);
assert.doesNotMatch(completedHtml, /private_tool/);

const mixed = projection.normalize({
  status: "COMPLETED",
  result: {
    type: "composite_result",
    data_profile: {primary: "composite", kinds: ["composite"]},
    view: {
      schema_version: "spatial-agent.composite-view.v1",
      data_kinds: ["vector", "raster", "metrics", "timeseries", "document_evidence"],
      answer: {headline: "综合结果", summary: "空间、指标和来源结果已汇总。"},
      sections: [
        {kind: "component", component_id: "map", data_profile: {primary: "vector", kinds: ["vector"]}},
        {kind: "component", component_id: "trend", data_profile: {primary: "timeseries", kinds: ["timeseries", "metrics"]}},
        {kind: "component", component_id: "source", data_profile: {primary: "document_evidence", kinds: ["document_evidence"]}},
      ],
    },
  },
});
assert.deepEqual(mixed.result_kinds.map(item => item.id), ["vector", "raster", "metrics", "timeseries", "document_evidence"]);
assert.equal(mixed.sections[1].data_kinds[0], "timeseries");
assert.match(projection.render(mixed), /结果组成/);
assert.match(projection.render(mixed), /矢量、栅格、指标、时间序列、文档证据/);

const clarification = projection.normalize({
  status: "NEEDS_CLARIFICATION",
  clarification: {state: "needs_clarification", missing: ["时间范围", "指标"], next_actions: ["请补充统计周期"]},
  plan_evidence: {selection_evidence: {schema_version: "spatial-agent.selection-evidence.v1", state: "clarification", clarification: {state: "needs_clarification", message: "请补充统计周期"}, next_actions: ["请补充统计周期"]}},
  result: {type: "unknown"},
});
assert.equal(clarification.phases[1].state, "active");
const clarificationHtml = projection.render(clarification);
assert.match(clarificationHtml, /需要补充的信息/);
assert.match(clarificationHtml, /时间范围/);
assert.match(clarificationHtml, /请补充统计周期/);
assert.ok(clarificationHtml.length < 12000);

const componentClarification = projection.normalize({
  status: "NEEDS_CLARIFICATION",
  component_fact_handoff: {
    state: "required",
    missing_fields: [
      {component_id: "economic-main", label: "经济指标", kind: "constraint"},
      {component_id: "economic-main", label: "分析区域", kind: "entity"},
    ],
    continuation: {token: "must-not-render"},
  },
  result: {type: "composite_result"},
});
assert.equal(componentClarification.clarification.state, "component_facts_required");
assert.match(projection.render(componentClarification), /经济指标/);
assert.doesNotMatch(projection.render(componentClarification), /must-not-render/);

const compositeClarification = projection.normalize({
  status: "NEEDS_CLARIFICATION",
  composite_fact_handoff: {
    state: "required",
    components: [
      {component_id: "economic-main", missing_fields: [{label: "经济指标", kind: "constraint"}]},
      {component_id: "gis-main", missing_fields: [{label: "行政区名称", kind: "entity"}]},
    ],
    continuation: {token: "must-not-render-composite"},
  },
});
assert.equal(compositeClarification.clarification.state, "component_facts_required");
assert.match(projection.render(compositeClarification), /行政区名称/);
assert.doesNotMatch(projection.render(compositeClarification), /must-not-render-composite/);

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

const providerFailure = projection.normalize({
  status: "FAILED",
  failure: {
    schema_version: "spatial-agent.failure.v1",
    status: "FAILED",
    category: "provider",
    phase: "planning",
    code: "provider_timeout",
    retryable: true,
  },
  next_actions: ["稍后重试"],
});
assert.equal(providerFailure.status_label, "模型暂时不可用");
assert.equal(providerFailure.failure.retryable, true);
assert.equal(providerFailure.phases[2].state, "unavailable");
assert.match(projection.render(providerFailure), /模型暂时不可用/);
assert.match(projection.render(providerFailure), /还没有开始执行分析任务/);

const planningFailures = [
  {
    payload: {
      status: "NEEDS_CLARIFICATION",
      planning_failure: {state: "clarification", code: "request_facts_missing", next_actions: ["补充指标和时间范围"]},
    },
    statusLabel: "等待补充",
    phaseIndex: 1,
    phaseState: "active",
    text: "补充指标和时间范围",
  },
  {
    payload: {
      status: "REJECTED",
      result: {planning_failure: {state: "preview_invalid", code: "taskplan_component_preview_invalid"}},
    },
    statusLabel: "计划未生成",
    phaseIndex: 2,
    phaseState: "unavailable",
    text: "计划格式不完整",
  },
  {
    payload: {
      status: "FAILED",
      plan_evidence: {planning_failure: {state: "binding_failed", code: "execution_binding_plan_missing", next_actions: ["重新生成计划"]}},
    },
    statusLabel: "计划未通过校验",
    phaseIndex: 2,
    phaseState: "unavailable",
    text: "计划校验未通过",
  },
];
for (const item of planningFailures) {
  const normalized = projection.normalize(item.payload);
  assert.equal(normalized.status_label, item.statusLabel);
  assert.equal(normalized.phases[item.phaseIndex].state, item.phaseState);
  const html = projection.render(normalized);
  assert.match(html, new RegExp(item.text));
  assert.doesNotMatch(html, /taskplan_component|execution_binding_plan_missing|request_facts_missing/);
}

console.log(JSON.stringify({status: "ok", cases: ["completed_projection", "mixed_result_kinds", "clarification_projection", "component_clarification_projection", "composite_clarification_projection", "repair_projection", "provider_failure_projection", "planning_failure_projection"]}));
