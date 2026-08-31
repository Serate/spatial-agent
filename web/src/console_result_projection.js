/* Domain-neutral, user-facing projection for the result workspace. */
(function attachConsoleResultProjection(root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ConsoleResultProjection = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function createModule() {
  const SCHEMA_VERSION = "spatial-agent.console-result-projection.v1";
  const COMPOSITE_VIEW_SCHEMA_VERSION = "spatial-agent.composite-view.v1";
  const RESULT_SUMMARY_SCHEMA_VERSION = "spatial-agent.result-summary.v1";
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
  const summaryStateLabels = Object.freeze({
    complete: "已完成", partial: "部分完成", pending: "生成中",
    waiting_decision: "等待确认", blocked: "暂时阻塞", unavailable: "不可用",
  });

  function normalize(input) {
    const data = record(input) ? input : {};
    const result = record(data.result) ? data.result : {};
    const composite = [data.view, result.view].find(value => (
      record(value) && value.schema_version === COMPOSITE_VIEW_SCHEMA_VERSION
    )) || null;
    const compositeAnswer = record(composite?.answer) ? composite.answer : {};
    const resultSummary = normalizeResultSummary(
      firstRecord(data.result_summary, result.result_summary, composite?.result_summary),
    );
    const answer = normalizeAnswer(compositeAnswer, data, result, composite, resultSummary);
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
    const analysisIntents = normalizeAnalysisIntents(
      firstList(
        planning?.analysis_intents,
        data.analysis_intents,
        result.analysis_intents,
        composite?.planning?.analysis_intents,
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
    const failure = normalizeFailure(
      firstRecord(data.failure, result.failure, composite?.failure, evidence.failure),
    );
    const planningFailure = normalizePlanningFailure(
      firstRecord(
        data.planning_failure,
        result.planning_failure,
        planning?.planning_failure,
        evidence.planning_failure,
      ),
    );
    const answerGeneration = firstRecord(
      composite?.evidence?.answer_generation,
      data.answer_generation_evidence,
      result.answer_generation_evidence,
      evidence.answer_generation,
    );
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
      status_label: statusLabelFor(status, failure, planningFailure),
      result_type: resultType,
      result_kind: kindLabels[result?.data_profile?.primary] || kindLabels["unknown"],
      result_kinds: resultKinds.map(kind => ({id: kind, label: kindLabels[kind] || "结构化结果"})),
      answer,
      context,
      discovery,
      selection_evidence: selectionEvidence,
      analysis_intents: analysisIntents,
      clarification,
      component_fact_handoff: handoff || {},
      composite_fact_handoff: compositeHandoff || {},
      continuation: continuation || {},
      planning,
      planning_failure: planningFailure,
      repair_lineage: repairLineage,
      plan,
      evidence,
      failure,
      answer_generation: answerGeneration || {},
      evidence_registry: evidenceRegistry,
      execution_binding: executionBinding || {},
      views,
      sections,
      artifacts,
      steps,
      view_count: viewCount,
      component_count: Math.max(0, Math.min(MAX_ITEMS, componentCount)),
      result_summary: resultSummary,
      phases: buildPhases({status, answer, resultSummary, context, clarification, planning, planningFailure, selectionEvidence, repairLineage, plan, evidence, evidenceRegistry, views, artifacts, steps, failure}),
    };
  }

  function normalizeAnswer(raw, data, result, composite, resultSummary) {
    const legacySummary = [data.answer, result.answer, data.error].find(value => typeof value === "string" && value.trim());
    const summary = text(raw.summary || resultSummary?.conclusion || legacySummary, 800);
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

  function normalizeResultSummary(raw) {
    const unavailable = {
      schema_version: RESULT_SUMMARY_SCHEMA_VERSION,
      state: "unavailable",
      conclusion: "",
      key_findings: [],
      limitations: [],
      evidence: {available: false, state: "unavailable", status: "unavailable", source_count: 0, sources: [], source_records: [], evidence_bundle: null, alignment: null},
      blocks: [],
      available: false,
    };
    if (!record(raw)) return unavailable;
    if (raw.schema_version && raw.schema_version !== RESULT_SUMMARY_SCHEMA_VERSION) {
      return {...unavailable, reason: "结果摘要版本暂不支持。"};
    }
    const blocks = list(raw.blocks).slice(0, 8).map((item, index) => normalizeSummaryBlock(item, index)).filter(Boolean);
    const evidence = normalizeSummaryEvidence(raw.evidence);
    return {
      schema_version: RESULT_SUMMARY_SCHEMA_VERSION,
      state: text(raw.state, 32) || "unavailable",
      conclusion: text(raw.conclusion || raw.summary, 800),
      key_findings: safeTextList(raw.key_findings, MAX_ITEMS),
      limitations: safeTextList(raw.limitations, MAX_ITEMS),
      evidence,
      blocks,
      available: Boolean(raw.conclusion || raw.key_findings || blocks.length || evidence.available),
    };
  }

  function normalizeSummaryBlock(raw, index) {
    if (!record(raw)) return null;
    const kinds = list(raw.kinds).filter(item => kindLabels[item]).slice(0, 4);
    const kind = kindLabels[raw.kind] ? raw.kind : (kinds[0] || "unknown");
    return {
      block_id: text(raw.block_id || "result-" + (index + 1), 96),
      title: text(raw.title || kindLabels[kind] || "结果", 160),
      kind,
      kind_label: kindLabels[kind] || "结构化结果",
      state: text(raw.state, 32) || "unavailable",
      conclusion: text(raw.conclusion || raw.summary, 480),
      facts: normalizeSummaryFacts(raw.facts),
      limitations: safeTextList(raw.limitations, 3),
      evidence: normalizeSummaryEvidence(raw.evidence),
    };
  }

  function normalizeSummaryEvidence(raw) {
    if (!record(raw)) return {available: false, state: "unavailable", status: "unavailable", source_count: 0, sources: [], source_records: []};
    const sourceCount = Number(raw.source_count);
    const sourceRecords = list(raw.source_records).slice(0, 8).map(normalizeSourceRecord).filter(Boolean);
    return {
      available: raw.available === true,
      state: text(raw.state, 32) || (raw.available === true ? "available" : "unavailable"),
      status: text(raw.status, 32) || (raw.available === true ? "ok" : "unavailable"),
      reason_code: text(raw.reason_code, 96),
      source_count: Number.isFinite(sourceCount) ? Math.max(0, Math.min(128, sourceCount)) : 0,
      sources: safeTextList(raw.sources, 4).filter(item => !/(prompt|token|secret|memory:\/\/|artifact:\/\/)/i.test(item)),
      source_records: sourceRecords,
      evidence_bundle: normalizeEvidenceBundle(raw.evidence_bundle),
      alignment: normalizeAlignment(raw.alignment),
      query: text(raw.query, 240),
      allowed_domains: safeTextList(raw.allowed_domains, 8).filter(item => /^[a-z0-9.-]+$/i.test(item)),
    };
  }

  function normalizeSourceRecord(raw) {
    if (!record(raw)) return null;
    const rawUrl = text(raw.url, 2048);
    const locator = text(raw.locator, 2048);
    const kind = text(raw.kind, 48) || (rawUrl ? "web" : "unknown");
    const common = {
      source_id: text(raw.source_id, 80),
      kind,
      title: text(raw.title, 160) || "未命名来源",
      domain: text(raw.domain, 160),
      snippet: text(raw.snippet, 320),
      quality: normalizeSourceQuality(raw.quality),
    };
    let url = "";
    if (rawUrl || kind === "web") {
      try {
        const parsed = new URL(rawUrl);
        if (parsed.protocol !== "https:" || parsed.username || parsed.password || !parsed.hostname || parsed.hostname === "localhost") return null;
        parsed.hash = "";
        url = parsed.toString().slice(0, 2048);
      } catch (_) {
        return null;
      }
      return {...common, url, locator: url};
    }
    if (!locator || locator.startsWith("/") || locator.startsWith("\\") || !/^[A-Za-z0-9:._/-]+$/.test(locator)) return null;
    return {...common, locator};
  }

  function normalizeSourceQuality(raw) {
    if (!record(raw)) return null;
    const freshness = record(raw.freshness) ? raw.freshness : {};
    const status = ["available", "stale", "partial", "duplicate", "unavailable", "unknown"].includes(text(raw.status, 32))
      ? text(raw.status, 32) : "unknown";
    const freshnessState = ["fresh", "stale", "unknown"].includes(text(freshness.state, 24))
      ? text(freshness.state, 24) : "unknown";
    return {
      status,
      completeness: ["complete", "partial", "unknown"].includes(text(raw.completeness, 24)) ? text(raw.completeness, 24) : "unknown",
      freshness: {state: freshnessState},
      duplicate: raw.duplicate === true,
      reason_codes: safeTextList(raw.reason_codes, 4),
    };
  }

  function normalizeEvidenceBundle(raw) {
    if (!record(raw)) return null;
    const entries = list(raw.entries).slice(0, 16).map(normalizeSourceRecord).filter(Boolean);
    const quality = record(raw.quality_summary) ? raw.quality_summary : {};
    const statusCounts = record(quality.status_counts) ? quality.status_counts : {};
    const freshnessCounts = record(quality.freshness_counts) ? quality.freshness_counts : {};
    const count = value => Number.isFinite(Number(value)) ? Math.max(0, Math.min(16, Number(value))) : 0;
    return {
      entries,
      unique_count: Math.max(0, Math.min(16, Number(raw.unique_count) || entries.length)),
      duplicate_count: Math.max(0, Math.min(16, Number(raw.duplicate_count) || 0)),
      conflict_count: Math.max(0, Math.min(16, Number(raw.conflict_count) || 0)),
      limitations: safeTextList(raw.limitations, 4),
      quality_summary: {
        status_counts: statusCounts,
        freshness_counts: freshnessCounts,
        partial: count(statusCounts.partial),
        unavailable: count(statusCounts.unavailable),
        stale: count(freshnessCounts.stale),
        unknown: count(freshnessCounts.unknown),
      },
    };
  }

  function normalizeAlignment(raw) {
    if (!record(raw)) return null;
    const allowed = ["aligned", "conflict", "unknown", "not_applicable"];
    return {
      status: allowed.includes(text(raw.status, 24)) ? text(raw.status, 24) : "unknown",
      dimensions: safeTextList(raw.dimensions, 4),
    };
  }

  function normalizeSummaryFacts(raw, depth = 0) {
    if (!record(raw) || depth > 2) return {};
    const privateKeys = /^(api_key|authorization|credentials|password|secret|token|prompt|messages|raw_response|result_ref|artifact_ref|path|file_path|dataset_path|geometry|coordinates|features|geojson|views|plan|steps|tool|args|references|request|domain_id|fingerprint|capability_id|component_ids|depends_on|required|view_refs|result)$/i;
    const output = {};
    Object.entries(raw).slice(0, 12).forEach(([key, value]) => {
      if (privateKeys.test(key) || /password|secret|token/i.test(key)) return;
      const normalized = normalizeSummaryValue(value, depth + 1);
      if (normalized !== undefined) output[text(key, 64)] = normalized;
    });
    return output;
  }

  function normalizeSummaryValue(value, depth) {
    if (value === null || typeof value === "boolean") return value;
    if (typeof value === "number") return Number.isFinite(value) ? value : undefined;
    if (typeof value === "string") return text(value, 160);
    if (depth > 2) return undefined;
    if (Array.isArray(value)) return value.slice(0, 6).map(item => normalizeSummaryValue(item, depth + 1)).filter(item => item !== undefined);
    if (record(value)) return normalizeSummaryFacts(value, depth);
    return undefined;
  }

  function normalizeFailure(raw) {
    if (!record(raw)) return {};
    const categories = ["provider", "planning", "clarification", "rejected", "execution", "persistence", "control", "unknown"];
    const category = categories.includes(text(raw.category, 32)) ? text(raw.category, 32) : "unknown";
    return {
      schema_version: text(raw.schema_version || "spatial-agent.failure.v1", 96),
      status: text(raw.status, 32).toUpperCase(),
      category,
      phase: text(raw.phase, 32),
      retryable: raw.retryable === true,
      code: text(raw.code, 96),
    };
  }

  function normalizePlanningFailure(raw) {
    if (!record(raw)) return {};
    const states = ["clarification", "preview_invalid", "preview_failed", "binding_failed", "rejected"];
    const state = states.includes(text(raw.state, 32)) ? text(raw.state, 32) : "rejected";
    return {
      schema_version: text(raw.schema_version || "spatial-agent.planning-failure.v1", 96),
      state,
      code: text(raw.code, 96),
      phase: text(raw.phase || "planning", 32),
      retryable: raw.retryable === true,
      execution_run_created: raw.execution_run_created === true,
      next_actions: safeTextList(raw.next_actions, MAX_ITEMS),
    };
  }

  function statusLabelFor(status, failure, planningFailure) {
    if (status === "FAILED" && failure?.category === "provider") return "模型暂时不可用";
    if (planningFailure?.state === "clarification") return "等待补充";
    if (["preview_invalid", "preview_failed"].includes(planningFailure?.state)) return "计划未生成";
    if (["binding_failed", "rejected"].includes(planningFailure?.state)) return "计划未通过校验";
    if (status === "FAILED" && failure?.phase === "planning") return "暂时无法生成计划";
    return statusLabels[status] || status || "等待结果";
  }

  function normalizeProviderRuntime(raw) {
    if (!record(raw)) return {};
    const result = {schema_version: text(raw.schema_version || "spatial-agent.provider-runtime.v1", 96)};
    if (record(raw.health)) {
      const health = raw.health;
      result.health = {
        status: text(health.status, 24),
        network: text(health.network, 24),
        reason_code: text(health.reason_code, 96),
      };
    }
    if (record(raw.deadline)) {
      const deadline = raw.deadline;
      result.deadline = {
        state: text(deadline.state, 24),
        deadline_exceeded: deadline.deadline_exceeded === true,
        retryable: deadline.retryable === true,
        reason_code: text(deadline.reason_code, 96),
      };
    }
    return result;
  }

  function buildPhases(model) {
    const status = model.status;
    const hasContext = Boolean(Object.keys(model.context || {}).length || model.status);
    const planningFailed = ["FAILED", "REJECTED"].includes(status) && (
      ["preview_invalid", "preview_failed", "binding_failed", "rejected"].includes(model.planningFailure?.state)
      || model.planningFailure?.phase === "planning"
      || model.failure?.category === "provider"
      || model.failure?.category === "planning"
      || model.failure?.category === "rejected"
      || model.failure?.phase === "planning"
    );
    const hasPlan = !planningFailed && Boolean(
      list(model.plan.steps).length
      || Object.keys(model.planning || {}).length
      || status === "WAITING_FOR_DECISION"
    );
    const hasExecution = model.steps.length > 0 || ["COMPLETED", "PARTIAL", "FAILED", "CANCELLED", "TIMED_OUT"].includes(status);
    const hasAnswer = Boolean(
      (model.answer.summary && model.answer.summary !== "暂未形成可读结论。")
      || model.resultSummary?.conclusion,
    );
    const hasEvidence = Boolean(
      Object.keys(model.evidence || {}).length
      || Object.keys(model.evidenceRegistry || {}).length
      || model.views.length
      || model.artifacts.length
      || model.resultSummary?.evidence?.available,
    );
    const clarificationState = String(model.clarification.state || "").toLowerCase();
    const clarificationNeeded = status === "NEEDS_CLARIFICATION"
      || model.planningFailure?.state === "clarification"
      || clarificationState === "needs_clarification"
      || clarificationState === "component_facts_required"
      || clarificationState === "composite_facts_required";
    const failed = ["FAILED", "REJECTED", "BLOCKED", "CANCELLED", "TIMED_OUT"].includes(status);
    return [
      phase("理解请求", hasContext ? "complete" : "waiting"),
      phase("信息确认", clarificationNeeded ? "active" : (hasContext ? "not_needed" : "waiting")),
      phase("生成计划", planningFailed ? "unavailable" : (clarificationNeeded ? "waiting" : (hasPlan ? (status === "PLANNING" ? "active" : "complete") : "waiting"))),
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
    const analysisIntentHtml = renderAnalysisIntents(model.analysis_intents, escapeHtml);
    const summaryHtml = renderResultSummary(model.result_summary, escapeHtml);
    const hasSharedSummary = model.result_summary?.available === true;
    const findings = !hasSharedSummary && model.answer.key_findings.length ? '<section class="projection-section"><h4>关键发现</h4><ul>' + model.answer.key_findings.slice(0, MAX_ITEMS).map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul></section>' : "";
    const resultKinds = model.result_kinds.length > 1
      ? '<section class="projection-section projection-result-kinds"><h4>结果组成</h4><p>' + escapeHtml(model.result_kinds.map(item => item.label).join("、")) + '</p></section>'
      : "";
    const limitations = !hasSharedSummary && model.answer.limitations.length ? '<section class="projection-section projection-limitations"><h4>使用边界</h4><ul>' + model.answer.limitations.slice(0, MAX_ITEMS).map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul></section>' : "";
    const nextSteps = model.answer.next_steps.length ? '<section class="projection-section projection-next"><h4>建议下一步</h4><ul>' + model.answer.next_steps.slice(0, MAX_ITEMS).map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul></section>' : "";
    const failureHtml = renderFailure(model.failure, model.planning_failure, model.status, escapeHtml);
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
      + summaryHtml + discoveryHtml + selectionHtml + analysisIntentHtml + clarification + failureHtml + resultKinds + findings + limitations + nextSteps + '</div>';
  }

  function renderResultSummary(summary, escapeHtml) {
    if (!summary?.available) return "";
    const state = escapeHtml(summaryStateLabels[summary.state] || "处理中");
    const conclusion = summary.conclusion
      ? '<p class="result-summary-conclusion">' + escapeHtml(summary.conclusion) + '</p>'
      : '<p class="result-summary-conclusion muted">暂未形成完整结论。</p>';
    const findings = summary.key_findings.length
      ? '<div class="result-summary-findings"><h4>关键发现</h4><ul>' + summary.key_findings.slice(0, MAX_ITEMS).map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul></div>'
      : "";
    const blocks = summary.blocks.length
      ? '<div class="result-summary-blocks"><h4>结果明细</h4>' + summary.blocks.slice(0, 8).map(block => renderSummaryBlock(block, escapeHtml)).join("") + '</div>'
      : "";
    const limitations = summary.limitations.length
      ? '<div class="result-summary-limitations"><h4>使用边界</h4><ul>' + summary.limitations.slice(0, MAX_ITEMS).map(item => '<li>' + escapeHtml(item) + '</li>').join("") + '</ul></div>'
      : "";
    const evidence = renderSummaryEvidence(summary.evidence, escapeHtml);
    return '<section class="result-summary-card" data-result-summary-schema="' + escapeHtml(RESULT_SUMMARY_SCHEMA_VERSION) + '"><div class="result-summary-head"><h4>统一结果摘要</h4><span>' + state + '</span></div>' + conclusion + findings + blocks + limitations + evidence + '</section>';
  }

  function renderSummaryBlock(block, escapeHtml) {
    const facts = Object.entries(block.facts || {}).slice(0, 8).map(([key, value]) => '<div class="result-summary-fact"><span>' + escapeHtml(key) + '</span><b>' + escapeHtml(formatSummaryValue(value)) + '</b></div>').join("");
    const details = facts ? '<details><summary>查看数据详情</summary><div class="result-summary-facts">' + facts + '</div></details>' : "";
    const limitation = block.limitations?.length ? '<small class="result-summary-block-note">' + escapeHtml(block.limitations.join("；")) + '</small>' : "";
    const evidence = renderSummaryEvidence(block.evidence, escapeHtml, true);
    return '<article class="result-summary-block" data-summary-kind="' + escapeHtml(block.kind) + '"><div class="result-summary-block-head"><strong>' + escapeHtml(block.title) + '</strong><span>' + escapeHtml(block.kind_label) + '</span></div>' + (block.conclusion ? '<p>' + escapeHtml(block.conclusion) + '</p>' : '') + details + evidence + limitation + '</article>';
  }

  function renderSummaryEvidence(evidence, escapeHtml, compact = false) {
    if (!record(evidence)) return "";
    const stateLabels = {available: "来源可用", degraded: "来源部分可用", no_results: "没有找到来源", unavailable: "来源不可用", unknown: "来源状态未知"};
    const state = text(evidence.state, 32) || "unavailable";
    const label = stateLabels[state] || "来源状态未知";
    const count = Number.isFinite(Number(evidence.source_count)) ? Number(evidence.source_count) : 0;
    const reason = evidence.reason_code ? ' · ' + escapeHtml(evidence.reason_code) : '';
    const bundle = evidence.evidence_bundle;
    const recordSource = list(evidence.source_records).length ? evidence.source_records : list(bundle?.entries);
    const records = recordSource.slice(0, 8).map(item => {
      const title = escapeHtml(item.title || item.domain || "未命名来源");
      const domain = item.domain ? ' <small>' + escapeHtml(item.domain) + '</small>' : '';
      const snippet = item.snippet ? '<p>' + escapeHtml(item.snippet) + '</p>' : '';
      const target = item.url
        ? '<a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener noreferrer">' + title + '</a>'
        : '<span>' + title + '</span>';
      return '<li>' + target + domain + snippet + '</li>';
    }).join("");
    const sources = records ? '<ul class="result-summary-source-list">' + records + '</ul>' : '';
    const sourceNames = !records && evidence.sources?.length ? '<small>' + escapeHtml(evidence.sources.join("、")) + '</small>' : '';
    const query = !compact && evidence.query ? '<small>检索词：' + escapeHtml(evidence.query) + '</small>' : '';
    const quality = bundle?.quality_summary || {};
    const qualityText = [];
    if (quality.stale) qualityText.push('可能过期 ' + quality.stale + ' 项');
    if (quality.unknown) qualityText.push('时间未知 ' + quality.unknown + ' 项');
    if (quality.partial) qualityText.push('内容不完整 ' + quality.partial + ' 项');
    if (quality.unavailable) qualityText.push('不可用 ' + quality.unavailable + ' 项');
    if (bundle?.conflict_count) qualityText.push('存在来源差异');
    const bundleMeta = bundle ? '<small>已合并 ' + escapeHtml(bundle.unique_count) + ' 个来源' + (bundle.duplicate_count ? '，去重 ' + escapeHtml(bundle.duplicate_count) + ' 个' : '') + (qualityText.length ? ' · ' + escapeHtml(qualityText.join('，')) : '') + '</small>' : '';
    const alignment = evidence.alignment?.status && evidence.alignment.status !== 'not_applicable'
      ? '<small>跨域对齐：' + escapeHtml({aligned: '已对齐', conflict: '存在差异', unknown: '信息不足'}[evidence.alignment.status] || '未知') + '</small>' : '';
    const limitations = bundle?.limitations?.length ? '<small>' + escapeHtml(bundle.limitations.slice(0, 3).join('；')) + '</small>' : '';
    return '<div class="result-summary-evidence result-summary-evidence-' + escapeHtml(state) + '"><span>' + escapeHtml(label) + ' · ' + escapeHtml(count) + ' 项</span>' + reason + bundleMeta + alignment + limitations + query + sourceNames + sources + '</div>';
  }

  function formatSummaryValue(value) {
    if (value === null || value === undefined || value === "") return "-";
    if (typeof value === "boolean") return value ? "是" : "否";
    if (typeof value === "number" && Number.isFinite(value)) return value.toLocaleString("zh-CN", {maximumFractionDigits: 3});
    if (Array.isArray(value)) return value.map(item => formatSummaryValue(item)).join("、");
    if (record(value)) return Object.entries(value).slice(0, 6).map(([key, item]) => key + "：" + formatSummaryValue(item)).join("，");
    return text(value, 240);
  }

  function renderFailure(failure, planningFailure, status, escapeHtml) {
    if (!failure?.category && !planningFailure?.state && !["FAILED", "REJECTED"].includes(status)) return "";
    const copy = failure?.category === "provider"
      ? {title: "模型暂时不可用", message: "这次还没有开始执行分析任务，可以稍后重试。"}
      : planningFailure?.state === "preview_invalid"
        ? {title: "计划格式不完整", message: "领域没有返回可验证的计划，本次没有开始执行。"}
      : planningFailure?.state === "preview_failed"
        ? {title: "计划生成失败", message: "领域服务暂时没有生成计划，本次没有开始执行。"}
      : planningFailure?.state === "binding_failed"
        ? {title: "计划校验未通过", message: "生成的计划没有通过执行链路校验，本次没有开始执行。"}
      : failure?.phase === "planning" || failure?.category === "planning" || failure?.category === "rejected" || status === "REJECTED"
        ? {title: "暂时无法生成分析计划", message: "请补充清晰的分析目标、范围或必要条件后重新提交。"}
      : failure?.category === "execution"
        ? {title: "分析未完成", message: "计划已经生成，但执行没有完成；可以查看已保留的部分结果或稍后恢复。"}
      : {title: "分析未完成", message: "本次分析没有形成完整结果，请查看已保留的状态和证据。"};
    const actions = safeTextList(planningFailure?.next_actions, MAX_ITEMS);
    return '<section class="projection-section projection-failure"><h4>' + escapeHtml(copy.title) + '</h4><p>' + escapeHtml(copy.message) + '</p>'
      + (actions.length ? '<small>下一步：' + escapeHtml(actions.join("；")) + '</small>' : "") + '</section>';
  }

  function firstRecord(...values) {
    return values.find(value => record(value)) || null;
  }

  function firstList(...values) {
    return values.find(value => Array.isArray(value) && value.length) || [];
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
    if (record(compositePlanning) && !list(result.analysis_intents).length && list(compositePlanning.analysis_intents).length) {
      result.analysis_intents = [...compositePlanning.analysis_intents];
    }
    if (record(compositePlanning) && !record(result.provider_runtime) && record(compositePlanning.provider_runtime)) {
      result.provider_runtime = {...compositePlanning.provider_runtime};
    }
    if (record(compositePlanning) && !record(result.planner_attempt) && record(compositePlanning.planner_attempt)) {
      result.planner_attempt = {...compositePlanning.planner_attempt};
    }
    if (record(compositePlanning) && !record(result.canonical_plan) && record(compositePlanning.canonical_plan)) {
      result.canonical_plan = {...compositePlanning.canonical_plan};
    }
    if (record(compositePlanning) && !record(result.planning_failure) && record(compositePlanning.planning_failure)) {
      result.planning_failure = {...compositePlanning.planning_failure};
    }
    if (record(result.provider_runtime)) {
      result.provider_runtime = normalizeProviderRuntime(result.provider_runtime);
    }
    if (record(result.planner_attempt)) {
      result.planner_attempt = normalizePlannerAttempt(result.planner_attempt);
    }
    if (record(result.canonical_plan)) {
      result.canonical_plan = normalizeCanonicalPlan(result.canonical_plan);
    }
    return Object.keys(result).length ? result : null;
  }

  function normalizeCanonicalPlan(raw) {
    if (!record(raw)) return {};
    const states = ["executable", "deferred", "unavailable"];
    const state = states.includes(text(raw.state, 24)) ? text(raw.state, 24) : "unavailable";
    const bounded = value => Number.isFinite(Number(value)) ? Math.max(0, Math.min(MAX_ITEMS, Number(value))) : 0;
    return {
      schema_version: text(raw.schema_version || "spatial-agent.canonical-plan-receipt.v1", 96),
      state,
      reason_code: text(raw.reason_code, 96),
      executable: state === "executable" && raw.executable === true,
      component_count: bounded(raw.component_count),
      materialized_count: bounded(raw.materialized_count),
      component_ids: safeTextList(raw.component_ids, MAX_ITEMS),
      request_fingerprint: text(raw.request_fingerprint, 128),
      binding_fingerprint: text(raw.binding_fingerprint, 128),
    };
  }

  function normalizePlannerAttempt(raw) {
    if (!record(raw)) return {};
    const stages = ["discovery", "selection", "execution", "repair"];
    const states = ["not_started", "in_progress", "completed", "failed", "timed_out"];
    const outcomes = ["success", "needs_clarification", "rejected", "provider_failure", "execution_failure", "unknown"];
    const bounded = value => Number.isFinite(Number(value)) ? Math.max(0, Math.min(128, Number(value))) : 0;
    return {
      schema_version: text(raw.schema_version || "spatial-agent.planner-attempt.v1", 96),
      stage: stages.includes(text(raw.stage, 24)) ? text(raw.stage, 24) : "selection",
      state: states.includes(text(raw.state, 24)) ? text(raw.state, 24) : "not_started",
      outcome: outcomes.includes(text(raw.outcome, 32)) ? text(raw.outcome, 32) : "unknown",
      attempts: bounded(raw.attempts),
      retries: bounded(raw.retries),
      retryable: raw.retryable === true,
      next_actions: safeTextList(raw.next_actions, 4),
      reason_code: text(raw.reason_code, 96),
      elapsed_ms: Number.isFinite(Number(raw.elapsed_ms)) ? Math.max(0, Math.min(3600000, Number(raw.elapsed_ms))) : null,
      budget: record(raw.budget) ? {
        envelope_max_bytes: boundedBudget(raw.budget.envelope_max_bytes, 1000000),
        envelope_bytes: boundedBudget(raw.budget.envelope_bytes, 1000000),
        output_max_tokens: boundedBudget(raw.budget.output_max_tokens, 2000000),
        provider_timeout_seconds: boundedBudget(raw.budget.provider_timeout_seconds, 86400),
        harness_timeout_seconds: boundedBudget(raw.budget.harness_timeout_seconds, 86400),
      } : {},
      repair: record(raw.repair) ? {
        attempted: raw.repair.attempted === true,
        count: bounded(raw.repair.count),
        max_attempts: bounded(raw.repair.max_attempts),
        state: text(raw.repair.state, 32),
      } : {},
    };
  }

  function boundedBudget(value, maximum) {
    return Number.isFinite(Number(value)) ? Math.max(0, Math.min(maximum, Number(value))) : null;
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

  function normalizeAnalysisIntents(raw) {
    return list(raw).slice(0, MAX_ITEMS).filter(record).map(item => {
      const intent = record(item.intent) ? item.intent : {};
      const operations = list(intent.operations).slice(0, MAX_ITEMS).filter(record).map(operation => ({
        kind: text(operation.kind, 48),
        output_kinds: normalizeKinds(operation.output_kinds),
      })).filter(operation => operation.kind);
      return {
        domain_id: text(item.domain_id, 64),
        schema_version: text(intent.schema_version, 96),
        operations,
        data_kinds: normalizeKinds(intent.data_kinds),
      };
    }).filter(item => item.operations.length || item.data_kinds.length);
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

  function renderAnalysisIntents(intents, escapeHtml) {
    if (!intents?.length) return "";
    const operationLabels = {
      query: "查询",
      filter: "筛选",
      aggregate: "汇总",
      trend: "趋势分析",
      compare: "区域对比",
      spatial_operation: "空间关系",
      evidence: "来源核验",
    };
    const operations = [...new Set(intents.flatMap(item => item.operations.map(operation => operationLabels[operation.kind] || "分析")))].slice(0, MAX_ITEMS);
    const kinds = [...new Set(intents.flatMap(item => item.data_kinds))]
      .filter(kind => kind !== "unknown")
      .slice(0, MAX_ITEMS);
    if (!operations.length && !kinds.length) return "";
    const rows = [];
    if (operations.length) rows.push('<p><strong>分析方式：</strong>' + escapeHtml(operations.join("、")) + '</p>');
    if (kinds.length) rows.push('<p><strong>结果类型：</strong>' + escapeHtml(kinds.map(kind => kindLabels[kind] || "结构化结果").join("、")) + '</p>');
    return '<section class="projection-section projection-analysis-intents"><h4>本次分析内容</h4>' + rows.join("") + '</section>';
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
