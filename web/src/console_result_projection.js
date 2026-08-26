/* Domain-neutral, user-facing projection for the result workspace. */
(function attachConsoleResultProjection(root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ConsoleResultProjection = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function createModule() {
  const SCHEMA_VERSION = "spatial-agent.console-result-projection.v1";
  const COMPOSITE_VIEW_SCHEMA_VERSION = "spatial-agent.composite-view.v1";
  const MAX_ITEMS = 6;
  const MAX_CHIPS = 8;
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
    let planning = mergePlanningEvidence(
      firstRecord(data.plan_evidence, result.planning, result.plan_evidence, data.planning),
      composite?.planning,
    );
    const planCompleteness = normalizePlanCompleteness(
      firstRecord(
        data.plan_completeness,
        result.plan_completeness,
        planning?.plan_completeness,
        composite?.planning?.plan_completeness,
      ),
    );
    if (planCompleteness) planning = {...(planning || {}), plan_completeness: planCompleteness};
    const repairLineage = normalizeRepairLineage(firstRecord(data.repair_lineage, result.repair_lineage, planning?.repair_lineage));
    const context = firstRecord(data.runtime_context, result.runtime_context, data.request_context, result.request_context);
    const discovery = normalizeDiscovery(firstRecord(planning?.discovery, context?.discovery));
    const selectionEvidence = normalizeSelectionEvidence(
      firstRecord(
        planning?.selection_evidence,
        data.selection_evidence,
        result.selection_evidence,
      ),
    );
    let clarification = firstRecord(data.clarification, result.clarification, composite?.clarification) || {};
    const componentHandoff = firstRecord(data.component_fact_handoff, result.component_fact_handoff);
    const compositeHandoff = firstRecord(data.composite_fact_handoff, result.composite_fact_handoff);
    const handoff = componentHandoff || compositeHandoff;
    const missingFields = list(handoff?.missing_fields).length
      ? list(handoff.missing_fields)
      : list(compositeHandoff?.components).flatMap(item => list(item?.missing_fields)).slice(0, MAX_ITEMS * 8);
    if (record(handoff) && missingFields.length) {
      clarification = {
        ...clarification,
        state: clarification.state || "component_facts_required",
        missing_fields: missingFields.slice(0, MAX_ITEMS * 8),
        next_actions: list(clarification.next_actions).length
          ? clarification.next_actions
          : ["补充后重新生成计划"],
      };
    }
    const continuation = firstRecord(data.continuation, result.continuation, handoff?.continuation);
    const evidence = firstRecord(composite?.evidence, result.evidence, data.evidence) || {};
    const evidenceRegistry = firstRecord(result.evidence_registry, data.evidence_registry) || {};
    const executionBinding = firstRecord(
      data.execution_binding,
      result.execution_binding,
      planning?.execution_binding,
      composite?.planning?.execution_binding,
      composite?.execution_binding,
      evidence?.execution_binding,
    );
    const plan = firstRecord(data.plan, result.plan) || {};
    const views = list(composite?.views).length ? list(composite.views) : Object.entries(result.views?.panels || {}).map(([id, value]) => ({view_id: id, ...value}));
    const sections = normalizeSections(composite?.sections);
    const steps = list(data.steps).length ? list(data.steps) : list(result.steps);
    const artifacts = list(composite?.artifacts).length ? list(composite.artifacts) : list(result.artifacts || data.artifacts);
    const resultType = text(result.type || data.result_type || data.plan?.output?.type || "unknown", 96) || "unknown";
    const resultKinds = normalizeKinds(
      composite?.data_kinds || result?.data_profile?.kinds || [],
    );
    const status = text(data.status || result.status || composite?.status || "", 40).toUpperCase();
    const viewCount = views.filter(item => record(item) && item.state !== "unavailable").length;
    const componentCount = Number(composite?.evidence?.component_count || sections.filter(item => item?.kind === "component").length || 0);
    return {
      schema_version: SCHEMA_VERSION,
      status,
      status_label: statusLabels[status] || status || "等待结果",
      result_type: resultType,
      result_kind: kindLabels[result?.data_profile?.primary] || kindLabels["unknown"],
      result_kinds: resultKinds.map(kind => ({id: kind, label: kindLabels[kind] || "结构化结果"})),
      answer,
      context,
      discovery,
      selection_evidence: selectionEvidence,
      clarification,
      component_fact_handoff: handoff || {},
      composite_fact_handoff: compositeHandoff || {},
      continuation: continuation || {},
      planning,
      repair_lineage: repairLineage,
      plan,
      evidence,
      evidence_registry: evidenceRegistry,
      execution_binding: executionBinding || {},
      views,
      sections,
      artifacts,
      steps,
      view_count: viewCount,
      component_count: Math.max(0, Math.min(MAX_ITEMS, componentCount)),
      phases: buildPhases({status, answer, context, clarification, planning, selectionEvidence, repairLineage, plan, evidence, evidenceRegistry, views, artifacts, steps}),
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
    const clarificationState = String(model.clarification.state || "").toLowerCase();
    const clarificationNeeded = status === "NEEDS_CLARIFICATION"
      || clarificationState === "needs_clarification"
      || clarificationState === "component_facts_required"
      || clarificationState === "composite_facts_required";
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
    if (model.result_kinds.length > 1) chips.push("包含：" + model.result_kinds.map(item => item.label).join("、"));
    if (model.steps.length) chips.push("已处理 " + model.steps.length + " 个步骤");
    else if (model.status === "COMPLETED" && !Object.keys(model.planning || {}).length) chips.push("直接形成结论");
    if (model.view_count) chips.push("包含 " + model.view_count + " 个结果视图");
    if (model.component_count) chips.push("覆盖 " + model.component_count + " 个分析部分");
    if (model.planning?.plan_completeness?.status === "valid") chips.push("计划已验证");
    else if (model.planning?.plan_completeness?.status === "degraded") chips.push("计划需要补充");
    if (model.execution_binding?.binding_fingerprint) chips.push("执行链路已核验");
    if (model.planning?.structured_output?.schema_enforced === true) chips.push("计划格式已确认");
    if (Object.keys(model.context || {}).length) chips.push("分析上下文已建立");
    if (Object.keys(model.evidence || {}).length || Object.keys(model.evidence_registry || {}).length) chips.push("证据已保留");
    if (model.repair_lineage.status === "repaired") chips.push("计划已校正");
    else if (model.repair_lineage.status === "failed") chips.push("计划校正未完成");
    const chipHtml = chips.slice(0, MAX_CHIPS).map(item => '<span class="result-chip">' + escapeHtml(item) + '</span>').join("");
    const discoveryHtml = renderDiscovery(model.discovery, escapeHtml);
    const selectionHtml = renderSelectionEvidence(model.selection_evidence, escapeHtml);
    const findings = model.answer.key_findings.length ? '<section class="projection-section"><h4>关键发现</h4><ul>' + model.answer.key_findings.slice(0, MAX_ITEMS).map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul></section>' : "";
    const resultKinds = model.result_kinds.length > 1
      ? '<section class="projection-section projection-result-kinds"><h4>结果组成</h4><p>' + escapeHtml(model.result_kinds.map(item => item.label).join("、")) + '</p></section>'
      : "";
    const limitations = model.answer.limitations.length ? '<section class="projection-section projection-limitations"><h4>使用边界</h4><ul>' + model.answer.limitations.slice(0, MAX_ITEMS).map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul></section>' : "";
    const nextSteps = model.answer.next_steps.length ? '<section class="projection-section projection-next"><h4>建议下一步</h4><ul>' + model.answer.next_steps.slice(0, MAX_ITEMS).map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul></section>' : "";
    const missing = safeTextList(
      model.clarification.missing || model.clarification.missing_fields,
      MAX_ITEMS,
    );
    const clarificationActions = safeTextList(model.clarification.next_actions, MAX_ITEMS);
    const clarificationState = String(model.clarification.state || "").toLowerCase();
    const needsClarification = model.status === "NEEDS_CLARIFICATION"
      || clarificationState === "needs_clarification"
      || clarificationState === "component_facts_required"
      || clarificationState === "composite_facts_required";
    const clarification = needsClarification ? '<section class="projection-section projection-clarification"><h4>需要补充的信息</h4>'
      + (missing.length ? '<ul>' + missing.map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul>' : '<p>请补充问题中的关键范围或条件。</p>')
      + (clarificationActions.length ? '<small>下一步：' + escapeHtml(clarificationActions.join("；")) + '</small>' : "") + '</section>' : "";
    return '<div class="result-projection" data-projection-schema="' + escapeHtml(SCHEMA_VERSION) + '"><ol class="result-phases" aria-label="分析阶段">' + phases + '</ol>'
      + (chipHtml ? '<div class="result-chips" aria-label="结果摘要">' + chipHtml + '</div>' : "")
      + discoveryHtml + selectionHtml + clarification + resultKinds + findings + limitations + nextSteps + '</div>';
  }

  function firstRecord(...values) {
    return values.find(value => record(value)) || null;
  }

  function mergePlanningEvidence(primary, compositePlanning) {
    const result = record(primary) ? {...primary} : {};
    if (record(compositePlanning) && !record(result.structured_output) && record(compositePlanning.structured_output)) {
      result.structured_output = {...compositePlanning.structured_output};
    }
    if (record(compositePlanning) && !record(result.plan_completeness) && record(compositePlanning.plan_completeness)) {
      result.plan_completeness = {...compositePlanning.plan_completeness};
    }
    if (record(compositePlanning) && !record(result.execution_binding) && record(compositePlanning.execution_binding)) {
      result.execution_binding = {...compositePlanning.execution_binding};
    }
    if (record(compositePlanning) && !record(result.selection_evidence) && record(compositePlanning.selection_evidence)) {
      result.selection_evidence = {...compositePlanning.selection_evidence};
    }
    return Object.keys(result).length ? result : null;
  }

  function normalizePlanCompleteness(raw) {
    if (!record(raw)) return null;
    const statuses = ["valid", "degraded", "failed", "unknown"];
    const status = statuses.includes(text(raw.status, 24)) ? text(raw.status, 24) : "unknown";
    const boundedCount = value => Number.isFinite(Number(value)) ? Math.max(0, Math.min(MAX_ITEMS, Number(value))) : 0;
    return {
      schema_version: text(raw.schema_version || "spatial-agent.plan-completeness.v1", 96),
      status,
      reason_code: text(raw.reason_code, 96),
      component_count: boundedCount(raw.component_count),
      materialized_count: boundedCount(raw.materialized_count),
    };
  }

  function normalizeDiscovery(raw) {
    if (!record(raw)) return {visible: false, state: "", state_label: "", candidate_count: 0, data_requirement_count: 0, next_actions: []};
    const labels = {
      ready: "能力与数据已发现",
      needs_facts: "需要补充信息",
      data_unavailable: "数据暂不可用",
      capability_unavailable: "暂时没有可执行能力",
    };
    const state = text(raw.state, 32).toLowerCase();
    const count = value => Number.isFinite(Number(value)) ? Math.max(0, Math.min(MAX_ITEMS * 4, Number(value))) : 0;
    return {
      visible: Boolean(raw.schema_version || state),
      schema_version: text(raw.schema_version, 96),
      state,
      state_label: labels[state] || "能力与数据准备状态",
      reason_code: text(raw.reason_code, 96),
      candidate_count: count(raw.candidate_count),
      data_requirement_count: count(raw.data_requirement_count),
      next_actions: safeTextList(raw.next_actions, 2),
    };
  }

  function normalizeSelectionEvidence(raw) {
    if (!record(raw)) {
      return {
        visible: false,
        state: "",
        state_label: "",
        reason_code: "",
        candidate_count: 0,
        selected_capability_keys: [],
        candidates: [],
        clarification: {},
        next_actions: [],
      };
    }
    const labels = {
      selected: "已选择分析能力",
      clarification: "等待确认分析能力",
      failed: "能力选择未完成",
      unavailable: "暂时无法选择分析能力",
      rejected: "分析能力选择已拒绝",
    };
    const candidates = list(raw.candidates).slice(0, MAX_ITEMS).filter(record).map(item => ({
      selection_key: text(item.selection_key, 140),
      label: text(item.label, 160),
      available: item.available !== false,
      execution_ready: item.execution_ready !== false,
      execution_readiness: text(item.execution_readiness, 32),
      data_profiles: list(item.data_profiles).slice(0, MAX_ITEMS).filter(record).map(profile => ({
        primary: text(profile.primary, 32),
        kinds: normalizeKinds(profile.kinds),
      })),
    }));
    const clarification = record(raw.clarification) ? {
      state: text(raw.clarification.state, 32),
      message: text(raw.clarification.message, 480),
      missing_by_domain: list(raw.clarification.missing_by_domain).slice(0, MAX_ITEMS),
      next_actions: safeTextList(raw.clarification.next_actions, MAX_ITEMS),
    } : {};
    return {
      visible: Boolean(raw.schema_version || raw.state),
      schema_version: text(raw.schema_version, 96),
      state: text(raw.state, 32).toLowerCase(),
      state_label: labels[text(raw.state, 32).toLowerCase()] || "能力选择状态",
      reason_code: text(raw.reason_code, 96),
      candidate_count: Number.isFinite(Number(raw.candidate_count)) ? Math.max(0, Math.min(MAX_ITEMS * 2, Number(raw.candidate_count))) : candidates.length,
      selected_capability_keys: safeTextList(raw.selected_capability_keys, MAX_ITEMS),
      candidates,
      clarification,
      next_actions: safeTextList(raw.next_actions, MAX_ITEMS),
    };
  }

  function normalizeKinds(raw) {
    const values = typeof raw === "string" ? [raw] : list(raw);
    const supported = ["vector", "raster", "metrics", "timeseries", "document_evidence", "composite", "text", "unknown"];
    const seen = new Set();
    return values.map(item => text(item, 48)).filter(item => supported.includes(item) && !seen.has(item) && seen.add(item)).slice(0, 8);
  }

  function normalizeSections(raw) {
    return list(raw).slice(0, MAX_ITEMS * 2).filter(record).map(item => ({
      section_id: text(item.section_id, 96),
      kind: text(item.kind, 48),
      title: text(item.title, 160),
      component_id: text(item.component_id, 96),
      domain_id: text(item.domain_id, 64),
      state: text(item.state, 32),
      status: text(item.status, 32),
      result_type: text(item.result_type, 96),
      data_profile: record(item.data_profile) ? item.data_profile : {},
      data_kinds: normalizeKinds(item.data_kinds || item.data_profile?.kinds),
      depends_on: safeTextList(item.depends_on, MAX_ITEMS),
      inputs: list(item.inputs).slice(0, MAX_ITEMS),
      answer: text(item.answer, 640),
      view_refs: safeTextList(item.view_refs, MAX_ITEMS),
    }));
  }

  function renderDiscovery(discovery, escapeHtml) {
    if (!discovery?.visible) return "";
    const state = discovery.state || "unknown";
    const detail = state === "ready"
      ? "已找到 " + discovery.candidate_count + " 个候选能力，涉及 " + discovery.data_requirement_count + " 项数据需求。"
      : state === "needs_facts"
        ? "已找到相关能力，但还缺少开始规划所需的信息。"
        : state === "data_unavailable"
          ? "能力存在，但数据覆盖或后端就绪状态暂时不满足要求。"
          : state === "capability_unavailable"
            ? "当前目录中没有可执行的匹配能力。"
            : "系统正在确认可用能力和数据状态。";
    const actions = discovery.next_actions.length
      ? '<small>下一步：' + escapeHtml(discovery.next_actions.join("；")) + '</small>'
      : "";
    return '<section class="projection-section projection-discovery" data-discovery-state="' + escapeHtml(state) + '"><h4>能力与数据准备</h4><p><strong>' + escapeHtml(discovery.state_label) + '</strong> · ' + escapeHtml(detail) + '</p>' + actions + '</section>';
  }

  function renderSelectionEvidence(selection, escapeHtml) {
    if (!selection?.visible) return "";
    const byKey = Object.fromEntries(selection.candidates.map(item => [item.selection_key, item]));
    const selectedLabels = selection.selected_capability_keys
      .map(key => byKey[key]?.label)
      .filter(Boolean)
      .slice(0, MAX_ITEMS);
    const selected = selectedLabels.length
      ? "已选择：" + selectedLabels.join("、")
      : selection.state_label;
    const clarification = selection.clarification?.message && selection.state !== "selected"
      ? '<p>' + escapeHtml(selection.clarification.message) + '</p>'
      : "";
    const actions = selection.next_actions.length
      ? '<small>下一步：' + escapeHtml(selection.next_actions.join("；")) + '</small>'
      : "";
    return '<section class="projection-section projection-selection" data-selection-state="' + escapeHtml(selection.state) + '"><h4>分析能力</h4><p><strong>' + escapeHtml(selected) + '</strong></p>' + clarification + actions + '</section>';
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
