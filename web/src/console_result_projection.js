/* Domain-neutral, user-facing projection for the result workspace. */
(function attachConsoleResultProjection(root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ConsoleResultProjection = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function createModule() {
  const SCHEMA_VERSION = "spatial-agent.console-result-projection.v1";
  const COMPOSITE_VIEW_SCHEMA_VERSION = "spatial-agent.composite-view.v1";
  const MAX_ITEMS = 6;
  const MAX_TEXT = 480;
  const record = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
  const list = value => Array.isArray(value) ? value : [];
  const text = (value, limit = MAX_TEXT) => String(value ?? "").replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, limit);
  const defaultEscape = value => text(value, 1200).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);

  const statusLabels = Object.freeze({
    COMPLETED: "已完成", PARTIAL: "部分完成", NEEDS_CLARIFICATION: "等待补充",
    WAITING_FOR_DECISION: "等待确认", PLANNING: "规划中", PLANNED: "计划已生成",
    EXECUTING: "执行中", QUEUED: "排队中", FAILED: "执行失败", REJECTED: "已拒绝",
    BLOCKED: "暂时阻塞", CANCELLED: "已取消", TIMED_OUT: "已超时",
  });
  const kindLabels = Object.freeze({
    vector: "矢量", raster: "栅格", metrics: "指标", timeseries: "时间序列",
    document_evidence: "文档证据", composite: "组合结果", text: "文本", unknown: "结构化结果",
  });

  function normalize(input) {
    const data = record(input) ? input : {};
    const result = record(data.result) ? data.result : {};
    const composite = [data.view, result.view].find(value => (
      record(value) && value.schema_version === COMPOSITE_VIEW_SCHEMA_VERSION
    )) || null;
    const compositeAnswer = record(composite?.answer) ? composite.answer : {};
    const answer = normalizeAnswer(compositeAnswer, data, result, composite);
    const planning = firstRecord(data.plan_evidence, result.planning, result.plan_evidence, data.planning);
    const repairLineage = normalizeRepairLineage(firstRecord(data.repair_lineage, result.repair_lineage, planning?.repair_lineage));
    const context = firstRecord(data.runtime_context, result.runtime_context, data.request_context, result.request_context);
    const clarification = firstRecord(data.clarification, result.clarification, composite?.clarification) || {};
    const evidence = firstRecord(composite?.evidence, result.evidence, data.evidence) || {};
    const evidenceRegistry = firstRecord(result.evidence_registry, data.evidence_registry) || {};
    const plan = firstRecord(data.plan, result.plan) || {};
    const views = list(composite?.views).length ? list(composite.views) : Object.entries(result.views?.panels || {}).map(([id, value]) => ({view_id: id, ...value}));
    const sections = list(composite?.sections);
    const steps = list(data.steps).length ? list(data.steps) : list(result.steps);
    const artifacts = list(composite?.artifacts).length ? list(composite.artifacts) : list(result.artifacts || data.artifacts);
    const resultType = text(result.type || data.result_type || data.plan?.output?.type || "unknown", 96) || "unknown";
    const status = text(data.status || result.status || composite?.status || "", 40).toUpperCase();
    const viewCount = views.filter(item => record(item) && item.state !== "unavailable").length;
    const componentCount = Number(composite?.evidence?.component_count || sections.filter(item => item?.kind === "component").length || 0);
    return {
      schema_version: SCHEMA_VERSION,
      status,
      status_label: statusLabels[status] || status || "等待结果",
      result_type: resultType,
      result_kind: kindLabels[result?.data_profile?.primary] || kindLabels["unknown"],
      answer,
      context,
      clarification,
      planning,
      repair_lineage: repairLineage,
      plan,
      evidence,
      evidence_registry: evidenceRegistry,
      views,
      sections,
      artifacts,
      steps,
      view_count: viewCount,
      component_count: Math.max(0, Math.min(MAX_ITEMS, componentCount)),
      phases: buildPhases({status, answer, context, clarification, planning, repairLineage, plan, evidence, evidenceRegistry, views, artifacts, steps}),
    };
  }

  function normalizeAnswer(raw, data, result, composite) {
    const legacySummary = [data.answer, result.answer, data.error].find(value => typeof value === "string" && value.trim());
    const summary = text(raw.summary || legacySummary, 800);
    const headline = text(raw.headline || result.title, 160);
    const findings = safeTextList(raw.key_findings, MAX_ITEMS);
    const sectionFindings = list(composite?.sections)
      .filter(item => item?.kind === "component")
      .map(item => text(item.answer, 320)).filter(Boolean);
    const limitations = safeTextList(raw.limitations, MAX_ITEMS);
    const nextSteps = safeTextList(raw.next_steps || data.next_actions || result.next_actions, MAX_ITEMS);
    return {
      headline: headline || "分析结果",
      summary: summary || "暂未形成可读结论。",
      key_findings: findings.length ? findings : sectionFindings.slice(0, MAX_ITEMS),
      limitations,
      next_steps: nextSteps,
    };
  }

  function buildPhases(model) {
    const status = model.status;
    const hasContext = Boolean(Object.keys(model.context || {}).length || model.status);
    const hasPlan = Boolean(list(model.plan.steps).length || Object.keys(model.planning || {}).length || status === "WAITING_FOR_DECISION");
    const hasExecution = model.steps.length > 0 || ["COMPLETED", "PARTIAL", "FAILED", "CANCELLED", "TIMED_OUT"].includes(status);
    const hasAnswer = Boolean(model.answer.summary && model.answer.summary !== "暂未形成可读结论。");
    const hasEvidence = Boolean(Object.keys(model.evidence || {}).length || Object.keys(model.evidenceRegistry || {}).length || model.views.length || model.artifacts.length);
    const clarificationNeeded = status === "NEEDS_CLARIFICATION" || String(model.clarification.state || "").toLowerCase() === "needs_clarification";
    const failed = ["FAILED", "REJECTED", "BLOCKED", "CANCELLED", "TIMED_OUT"].includes(status);
    return [
      phase("理解请求", hasContext ? "complete" : "waiting"),
      phase("信息确认", clarificationNeeded ? "active" : (hasContext ? "not_needed" : "waiting")),
      phase("生成计划", clarificationNeeded ? "waiting" : (hasPlan ? (status === "PLANNING" ? "active" : "complete") : "waiting")),
      phase("执行任务", failed ? "unavailable" : (status === "EXECUTING" || status === "QUEUED" ? "active" : (hasExecution ? "complete" : "waiting"))),
      phase("形成结论", hasAnswer ? "complete" : (failed ? "unavailable" : "waiting")),
      phase("保留证据", hasEvidence ? "complete" : (failed ? "unavailable" : "waiting")),
    ];
  }

  function phase(label, state) {
    return {label, state, state_label: {complete: "已完成", active: "进行中", waiting: "待处理", not_needed: "无需处理", unavailable: "不可用"}[state] || "未知"};
  }

  function render(modelOrData, options = {}) {
    const model = modelOrData?.schema_version === SCHEMA_VERSION ? modelOrData : normalize(modelOrData);
    const escapeHtml = typeof options.escapeHtml === "function" ? options.escapeHtml : defaultEscape;
    const phases = model.phases.map(item => '<li class="result-phase is-' + escapeHtml(item.state) + '" data-phase-state="' + escapeHtml(item.state) + '"><span class="result-phase-dot" aria-hidden="true"></span><span><b>' + escapeHtml(item.label) + '</b><small>' + escapeHtml(item.state_label) + '</small></span></li>').join("");
    const chips = [];
    if (model.result_kind && model.result_kind !== "结构化结果") chips.push(model.result_kind + "结果");
    if (model.steps.length) chips.push("已处理 " + model.steps.length + " 个步骤");
    else if (model.status === "COMPLETED") chips.push("直接形成结论");
    if (model.view_count) chips.push("包含 " + model.view_count + " 个结果视图");
    if (model.component_count) chips.push("覆盖 " + model.component_count + " 个分析部分");
    if (Object.keys(model.context || {}).length) chips.push("分析上下文已建立");
    if (Object.keys(model.evidence || {}).length || Object.keys(model.evidence_registry || {}).length) chips.push("证据已保留");
    if (model.repair_lineage.status === "repaired") chips.push("计划已校正");
    else if (model.repair_lineage.status === "failed") chips.push("计划校正未完成");
    const chipHtml = chips.slice(0, MAX_ITEMS).map(item => '<span class="result-chip">' + escapeHtml(item) + '</span>').join("");
    const findings = model.answer.key_findings.length ? '<section class="projection-section"><h4>关键发现</h4><ul>' + model.answer.key_findings.slice(0, MAX_ITEMS).map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul></section>' : "";
    const limitations = model.answer.limitations.length ? '<section class="projection-section projection-limitations"><h4>使用边界</h4><ul>' + model.answer.limitations.slice(0, MAX_ITEMS).map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul></section>' : "";
    const nextSteps = model.answer.next_steps.length ? '<section class="projection-section projection-next"><h4>建议下一步</h4><ul>' + model.answer.next_steps.slice(0, MAX_ITEMS).map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul></section>' : "";
    const missing = safeTextList(model.clarification.missing, MAX_ITEMS);
    const clarificationActions = safeTextList(model.clarification.next_actions, MAX_ITEMS);
    const needsClarification = model.status === "NEEDS_CLARIFICATION" || String(model.clarification.state || "").toLowerCase() === "needs_clarification";
    const clarification = needsClarification ? '<section class="projection-section projection-clarification"><h4>需要补充的信息</h4>'
      + (missing.length ? '<ul>' + missing.map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul>' : '<p>请补充问题中的关键范围或条件。</p>')
      + (clarificationActions.length ? '<small>下一步：' + escapeHtml(clarificationActions.join("；")) + '</small>' : "") + '</section>' : "";
    return '<div class="result-projection" data-projection-schema="' + escapeHtml(SCHEMA_VERSION) + '"><ol class="result-phases" aria-label="分析阶段">' + phases + '</ol>'
      + (chipHtml ? '<div class="result-chips" aria-label="结果摘要">' + chipHtml + '</div>' : "")
      + clarification + findings + limitations + nextSteps + '</div>';
  }

  function firstRecord(...values) {
    return values.find(value => record(value)) || null;
  }

  function normalizeRepairLineage(raw) {
    if (!record(raw)) return {status: "missing", attempted: false, count: 0, reason_code: ""};
    const statuses = ["not_attempted", "repaired", "failed", "skipped"];
    const status = statuses.includes(text(raw.status, 32)) ? text(raw.status, 32) : "unavailable";
    const count = Number.isFinite(Number(raw.count)) ? Math.max(0, Math.min(1, Number(raw.count))) : 0;
    return {
      schema_version: text(raw.schema_version, 96),
      status,
      attempted: raw.attempted === true,
      count,
      reason_code: text(raw.reason_code, 96),
      request_fingerprint: text(raw.request_fingerprint, 128),
    };
  }

  function safeTextList(value, limit) {
    const values = typeof value === "string" ? [value] : list(value);
    return values.map(item => {
      if (record(item)) return item.label || item.message || item.action || item.name || item.id || "";
      return item;
    }).map(item => text(item, 320)).filter(Boolean).slice(0, limit);
  }

  return Object.freeze({SCHEMA_VERSION, COMPOSITE_VIEW_SCHEMA_VERSION, normalize, render});
});
