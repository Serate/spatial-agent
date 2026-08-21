/*
 * Bounded Console seam for planner repair, rejection, and clarification
 * evidence.
 *
 * This module is intentionally independent from the Runtime and the DOM.  It
 * accepts current result envelopes as well as the evaluator's repair
 * projection, but only emits a small, allow-listed view model.  In
 * particular, provider payloads, exception messages, request text, and raw
 * ``error`` fields never cross this boundary.
 */
(function attachConsoleDecisionEvidence(root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ConsoleDecisionEvidence = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function createConsoleDecisionEvidence() {
  const VERSIONS = Object.freeze({
    replanning: "spatial-agent.replanning.v1",
    repairEvaluation: "spatial-agent.repair-evaluation.v1",
    clarification: "spatial-agent.clarification.v1",
    failure: "spatial-agent.failure.v1",
  });
  const LIMITS = Object.freeze({
    id: 80,
    code: 64,
    text: 180,
    events: 8,
    steps: 24,
    items: 8,
  });

  const STATUS_LABELS = Object.freeze({
    available: "可用",
    none: "未发生",
    missing: "未提供",
    unknown: "无法判定",
    unavailable: "不可用",
    partial: "部分可用",
    rejected: "已拒绝",
    needs_clarification: "需要澄清",
    not_applicable: "不适用",
  });
  const FAILURE_LABELS = Object.freeze({
    rejected: "请求已拒绝",
    policy: "策略拒绝",
    planning: "规划校验",
    tool_validation: "工具契约校验",
    provider: "模型服务",
    execution: "执行",
    clarification: "需要澄清",
    timeout: "超时",
    cancelled: "已取消",
    unknown: "受控失败",
  });
  const PHASE_LABELS = Object.freeze({
    planning: "规划阶段",
    execution: "执行阶段",
    control: "控制阶段",
    unknown: "未知阶段",
  });

  function isRecord(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function text(value, fallback, limit) {
    const valueText = (typeof value === "string" || typeof value === "number")
      ? String(value).replace(/[\u0000-\u001f\u007f]/g, " ").trim()
      : "";
    return (valueText || fallback).slice(0, limit);
  }

  function identifier(value, fallback) {
    const candidate = text(value, "", LIMITS.code).toLowerCase();
    return /^[a-z0-9][a-z0-9_.-]{0,63}$/.test(candidate) ? candidate : fallback;
  }

  function boundedList(value, limit, mapper) {
    if (!Array.isArray(value)) return [];
    return value.slice(0, limit).map(mapper).filter(Boolean);
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[character]));
  }

  function statusLabel(state) {
    return STATUS_LABELS[state] || "受控状态";
  }

  function repairSource(data, result) {
    const candidates = [
      ["evaluation", data.repair_evidence],
      ["evaluation", result.repair_evidence],
      ["replanning", result.replanning],
      ["replanning", data.replanning],
    ];
    for (const [kind, value] of candidates) {
      if (value !== undefined && value !== null) return {kind, value};
    }
    if (Array.isArray(data.replan_events)) {
      return {kind: "legacy", value: {events: data.replan_events}};
    }
    return null;
  }

  function repairEvent(event, ordinal) {
    if (!isRecord(event)) return null;
    const failedStep = text(event.failed_step_id, "", LIMITS.id);
    const failedTool = text(event.failed_tool, "", LIMITS.id);
    if (!failedStep || !failedTool) return null;
    const phase = ["planning", "execution"].includes(event.phase)
      ? event.phase
      : "unknown";
    const category = identifier(event.failure_category, "unknown");
    const replacementIds = boundedList(
      event.replanned_step_ids,
      LIMITS.steps,
      value => text(value, "", LIMITS.id),
    );
    const projected = {
      ordinal,
      phase,
      phase_label: PHASE_LABELS[phase],
      failed_step_id: failedStep,
      failed_tool: failedTool,
      failure_category: category,
      failure_category_label: FAILURE_LABELS[category] || "受控失败",
      replanned_step_ids: replacementIds,
      replanned_step_count: replacementIds.length,
    };
    if (typeof event.latency_ms === "number" && Number.isFinite(event.latency_ms) && event.latency_ms >= 0) {
      projected.latency_ms = Math.min(event.latency_ms, 86400000);
    }
    return projected;
  }

  function normalizeRepair(data, result) {
    const source = repairSource(data, result);
    if (!source) {
      return {
        state: "missing",
        available: false,
        count: 0,
        events: [],
        reason: "本次结果未提供计划修复证据，无法判断是否发生修复。",
        schema_version: null,
      };
    }
    if (!isRecord(source.value)) {
      return {
        state: "unavailable",
        available: false,
        count: 0,
        events: [],
        reason: "计划修复证据结构无效，已切换为有界状态。",
        schema_version: null,
      };
    }
    const raw = source.value;
    let schemaVersion = raw.schema_version;
    if (source.kind === "evaluation") {
      if (schemaVersion !== VERSIONS.repairEvaluation) {
        if (schemaVersion) {
          return {
            state: "unavailable", available: false, count: 0, events: [],
            reason: "计划修复证据使用未知版本，暂时无法安全展示。",
            schema_version: null,
          };
        }
        return {
          state: "unavailable", available: false, count: 0, events: [],
          reason: "计划修复证据缺少版本，暂时无法安全展示。",
          schema_version: null,
        };
      }
      const lineage = isRecord(raw.lineage) ? raw.lineage : null;
      if (!lineage || !Array.isArray(lineage.events)) {
        return {
          state: "unavailable", available: false, count: 0, events: [],
          reason: "计划修复证据缺少可读事件，已切换为有界状态。",
          schema_version: schemaVersion,
        };
      }
      // Keep the caller's payload immutable; the renderer only consumes the
      // projected event list below.
    } else if (source.kind === "replanning") {
      if (schemaVersion && schemaVersion !== VERSIONS.replanning) {
        return {
          state: "unavailable", available: false, count: 0, events: [],
          reason: "计划修复证据使用未知版本，暂时无法安全展示。",
          schema_version: null,
        };
      }
      schemaVersion = VERSIONS.replanning;
      if (!Array.isArray(raw.events)) {
        return {
          state: "unavailable", available: false, count: 0, events: [],
          reason: "计划修复证据缺少事件列表，已切换为有界状态。",
          schema_version: schemaVersion,
        };
      }
    } else {
      schemaVersion = null;
      if (!Array.isArray(raw.events)) {
        return {
          state: "unavailable", available: false, count: 0, events: [],
          reason: "历史计划修复证据不可读，已切换为有界状态。",
          schema_version: null,
        };
      }
    }
    const sourceEvents = source.kind === "evaluation"
      ? (isRecord(raw.lineage) && Array.isArray(raw.lineage.events) ? raw.lineage.events : [])
      : raw.events;
    const events = [];
    let invalidEvent = false;
    sourceEvents.slice(0, LIMITS.events).forEach((event, index) => {
      const projected = repairEvent(event, index + 1);
      if (projected) events.push(projected);
      else invalidEvent = true;
    });
    if (!events.length && invalidEvent) {
      return {
        state: "unavailable", available: false, count: 0, events: [],
        reason: "计划修复事件缺少安全字段，已切换为有界状态。",
        schema_version: schemaVersion,
      };
    }
    return {
      state: invalidEvent ? "partial" : (events.length ? "available" : "none"),
      available: events.length > 0,
      count: events.length,
      events,
      reason: invalidEvent ? "部分计划修复事件缺少安全字段，已隐藏不可读内容。" : "",
      schema_version: schemaVersion,
    };
  }

  function normalizeRejection(data, result, status) {
    if (status !== "REJECTED" && String(data.error_category || result.error_category || "").toLowerCase() !== "rejected") {
      return {state: "not_applicable", available: false, category: "", category_label: ""};
    }
    const failure = isRecord(data.failure) ? data.failure : (isRecord(result.failure) ? result.failure : {});
    const knownFailure = !failure.schema_version || failure.schema_version === VERSIONS.failure;
    const structuredFailure = knownFailure ? failure : {};
    const category = identifier(structuredFailure.category || data.error_category || result.error_category, "rejected");
    const phase = ["planning", "execution", "control"].includes(structuredFailure.phase) ? structuredFailure.phase : "planning";
    const code = identifier(structuredFailure.code || data.error_code || result.error_code, "request_rejected");
    return {
      state: "rejected",
      available: Object.keys(failure).length > 0,
      category,
      category_label: FAILURE_LABELS[category] || "请求已拒绝",
      code,
      phase,
      phase_label: PHASE_LABELS[phase] || "规划阶段",
      retryable: structuredFailure.retryable === true,
      reason: Object.keys(structuredFailure).length ? "已读取结构化拒绝证据。" : "未提供完整拒绝证据，已使用运行状态兜底。",
    };
  }

  function normalizeClarification(data, result, status) {
    const details = isRecord(data.clarification) ? data.clarification : (isRecord(result.clarification) ? result.clarification : null);
    if (status !== "NEEDS_CLARIFICATION" && !details) {
      return {state: "not_applicable", available: false, missing: [], next_actions: [], capabilities: []};
    }
    if (!details) {
      return {
        state: "unavailable", available: false, missing: [], next_actions: [], capabilities: [],
        reason: "当前请求需要澄清，但未提供结构化澄清证据。",
      };
    }
    if (details.schema_version && details.schema_version !== VERSIONS.clarification) {
      return {
        state: "unavailable", available: false, missing: [], next_actions: [], capabilities: [],
        reason: "澄清证据使用未知版本，暂时无法安全展示。",
      };
    }
    const state = ["matched_capability_missing_parameters", "unmatched_spatial_capability"].includes(details.state)
      ? details.state
      : "unknown";
    const missing = boundedList(details.missing, LIMITS.items, value => text(value, "", LIMITS.text));
    const nextActions = boundedList(details.next_actions, LIMITS.items, value => text(value, "", LIMITS.text));
    const capabilities = boundedList(
      details.matched_capabilities || details.suggested_capabilities,
      LIMITS.items,
      value => text(value, "", LIMITS.id),
    );
    return {
      state: "needs_clarification",
      available: true,
      detail_state: state,
      detail_state_label: state === "matched_capability_missing_parameters"
        ? "已识别能力，但参数不完整"
        : state === "unmatched_spatial_capability" ? "尚未匹配到已注册能力" : "需要补充信息",
      missing,
      next_actions: nextActions,
      capabilities,
      reason: "已读取结构化澄清证据。",
    };
  }

  function normalize(input) {
    const data = isRecord(input) ? input : {};
    const result = isRecord(data.result) ? data.result : {};
    const status = text(data.status || result.status, "", LIMITS.code).toUpperCase();
    const repair = normalizeRepair(data, result);
    const rejection = normalizeRejection(data, result, status);
    const clarification = normalizeClarification(data, result, status);
    return {
      status,
      visible: Boolean(status || repair.state !== "missing" || rejection.state !== "not_applicable" || clarification.state !== "not_applicable"),
      repair,
      rejection,
      clarification,
    };
  }

  function renderRepair(repair) {
    let content = "计划修复：" + statusLabel(repair.state);
    if (repair.state === "available" || repair.state === "partial") {
      content += " · " + repair.count + " 次";
      const events = repair.events.map(event =>
        "第" + event.ordinal + "次：" + event.phase_label + " · 失败步骤 " + event.failed_step_id +
        " · 工具 " + event.failed_tool + " · " + event.failure_category_label +
        " · 新增 " + event.replanned_step_count + " 步"
      );
      content += events.length ? "<ul>" + events.map(item => "<li>" + escapeHtml(item) + "</li>").join("") + "</ul>" : "";
    } else if (repair.reason) {
      content += "<p>" + escapeHtml(repair.reason) + "</p>";
    }
    return "<section class=\"decision-evidence-card decision-repair\" data-repair-state=\"" + escapeHtml(repair.state) + "\"><h4>计划修复</h4><div>" + content + "</div></section>";
  }

  function renderRejection(rejection) {
    if (rejection.state === "not_applicable") return "";
    const completeness = rejection.available ? "结构化证据可用" : "结构化证据不完整，已使用状态兜底";
    return "<section class=\"decision-evidence-card decision-rejection\" data-rejection-state=\"" + escapeHtml(rejection.state) + "\"><h4>拒绝证据</h4><div>请求已拒绝 · " + escapeHtml(rejection.category_label) + "</div><p>" + escapeHtml(completeness) + " · 阶段：" + escapeHtml(rejection.phase_label) + " · 代码：" + escapeHtml(rejection.code) + "</p></section>";
  }

  function renderClarification(clarification) {
    if (clarification.state === "not_applicable") return "";
    if (clarification.state !== "needs_clarification") {
      return "<section class=\"decision-evidence-card decision-clarification\" data-clarification-state=\"" + escapeHtml(clarification.state) + "\"><h4>澄清证据</h4><div>" + escapeHtml(clarification.reason || "澄清证据不可用，已使用有界状态。") + "</div></section>";
    }
    const list = values => values.length ? "<ul>" + values.map(item => "<li>" + escapeHtml(item) + "</li>").join("") + "</ul>" : "";
    return "<section class=\"decision-evidence-card decision-clarification\" data-clarification-state=\"needs_clarification\"><h4>澄清证据</h4><div>" + escapeHtml(clarification.detail_state_label) + "</div>" +
      (clarification.missing.length ? "<p>待补充</p>" + list(clarification.missing) : "") +
      (clarification.capabilities.length ? "<p>相关能力</p>" + list(clarification.capabilities) : "") +
      (clarification.next_actions.length ? "<p>下一步</p>" + list(clarification.next_actions) : "") +
      "</section>";
  }

  function render(input) {
    const model = normalize(input);
    if (!model.visible) return {model, html: ""};
    const cards = renderRepair(model.repair) + renderRejection(model.rejection) + renderClarification(model.clarification);
    return {
      model,
      html: "<div class=\"decision-evidence\" data-status=\"" + escapeHtml(model.status || "unknown") + "\"><div class=\"decision-evidence-head\"><strong>决策证据</strong><span>仅显示结构化、脱敏状态</span></div><div class=\"decision-evidence-grid\">" + cards + "</div></div>",
    };
  }

  return Object.freeze({LIMITS, VERSIONS, normalize, render});
});
