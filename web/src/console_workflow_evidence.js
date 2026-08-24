/*
 * Domain-neutral workflow composition projection for the Console.
 *
 * The server owns workflow selection and evidence contracts. This module is a
 * deliberately small renderer seam: it accepts a run/preview envelope,
 * normalizes bounded component identity and dependency data, and produces a
 * safe summary for the dynamic workspace. It never interprets a GIS tool or
 * constraint value.
 */
(function attachWorkflowEvidence(root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ConsoleWorkflowEvidence = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function createWorkflowEvidence() {
  const VERSION = "spatial-agent.workflow-evidence.v1";
  const MAX_COMPONENTS = 8;
  const MAX_ITEMS = 16;
  const MAX_TEXT = 160;
  const EVIDENCE_FIELDS = ["readiness", "coverage", "alignment", "provenance"];

  function record(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function text(value, fallback = "", limit = MAX_TEXT) {
    const normalized = value === null || value === undefined
      ? ""
      : String(value).replace(/[\u0000-\u001f\u007f]/g, " ").trim();
    return (normalized || fallback).slice(0, limit);
  }

  function list(value, limit = MAX_ITEMS) {
    return (Array.isArray(value) ? value : [])
      .map(item => text(item))
      .filter(Boolean)
      .filter((item, index, items) => items.indexOf(item) === index)
      .slice(0, limit);
  }

  function escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
    }[character]));
  }

  function cssState(value) {
    return text(value, "unknown", 32).toLowerCase().replace(/[^a-z0-9_-]/g, "-");
  }

  function sourceRecord(data) {
    const source = record(data) ? data : {};
    const envelope = record(source.result) ? source.result : {};
    const planning = record(source.plan_evidence)
      ? source.plan_evidence
      : record(envelope.planning) ? envelope.planning : {};
    const selection = record(planning.workflow_selection)
      ? planning.workflow_selection
      : record(envelope.workflow_selection) ? envelope.workflow_selection
        : record(source.workflow_selection) ? source.workflow_selection : {};
    const output = record(source.plan?.output)
      ? source.plan.output
      : record(envelope.output) ? envelope.output : {};
    return {source, envelope, planning, selection, output};
  }

  function normalizeEvidence(value) {
    const source = record(value) ? value : {};
    const result = {};
    for (const field of EVIDENCE_FIELDS) {
      const item = source[field];
      if (record(item)) {
        result[field] = {
          status: text(item.status, "unknown", 32),
          label: text(item.label || item.status, "未提供", 96),
          reason: text(item.reason || item.message, "", MAX_TEXT),
        };
      } else if (item !== undefined && item !== null && String(item).trim()) {
        result[field] = {status: text(item, "unknown", 32), label: text(item, "未提供", 96), reason: ""};
      }
    }
    if (source.status || source.reason || source.message) {
      result.status = text(source.status, "unknown", 32);
      result.reason = text(source.reason || source.message, "", MAX_TEXT);
    }
    return result;
  }

  function componentEvidence(source, component) {
    const direct = record(component.evidence_summary)
      ? component.evidence_summary
      : record(component.evidence_state) ? component.evidence_state : null;
    const collection = source.component_evidence;
    let projected = direct || {};
    if (Array.isArray(collection)) {
      const match = collection.find(item => record(item) && text(item.component_id) === component.component_id);
      if (record(match)) projected = {...projected, ...match};
    } else if (record(collection) && record(collection[component.component_id])) {
      projected = {...projected, ...collection[component.component_id]};
    }
    return normalizeEvidence(projected);
  }

  function normalizeComponent(item, index, source) {
    if (!record(item)) return null;
    const templateId = text(item.template_id || item.template || item.id);
    const componentId = text(item.component_id || item.id || templateId || `component-${index + 1}`);
    if (!templateId || !componentId) return null;
    const component = {
      component_id: componentId,
      template_id: templateId,
      template_version: text(item.template_version || item.version, "1.0.0", 48),
      depends_on_components: list(item.depends_on_components || item.depends_on, 8),
      constraint_keys: list(item.constraint_keys, MAX_ITEMS),
      evidence_keys: list(item.evidence_keys || (Array.isArray(item.evidence) ? item.evidence : []), MAX_ITEMS),
      evidence: componentEvidence(source, item),
      step_count: 0,
    };
    return component;
  }

  function normalize(data) {
    const {source, envelope, planning, selection, output} = sourceRecord(data);
    let rawComponents = selection.workflow_components || output.workflow_components || output.components;
    if (!Array.isArray(rawComponents) || !rawComponents.length) {
      const ids = list(selection.workflow_component_ids || output.workflow_component_ids, MAX_COMPONENTS);
      const templates = list(selection.workflow_component_template_ids || output.component_template_ids, MAX_COMPONENTS);
      rawComponents = ids.map((id, index) => ({component_id: id, template_id: templates[index] || id}));
    }
    const components = [];
    const seen = new Set();
    rawComponents.slice(0, MAX_COMPONENTS).forEach((item, index) => {
      const normalized = normalizeComponent(item, index, source);
      if (normalized && !seen.has(normalized.component_id)) {
        seen.add(normalized.component_id);
        components.push(normalized);
      }
    });
    const steps = Array.isArray(source.plan?.steps)
      ? source.plan.steps
      : Array.isArray(source.steps) ? source.steps : [];
    for (const step of steps.slice(0, 128)) {
      const id = text(step?.id || step?.step_id, "");
      const owner = id.split("--")[0];
      const component = components.find(item => item.component_id === owner);
      if (component) component.step_count += 1;
    }
    const dependencies = components.reduce((count, item) => count + item.depends_on_components.length, 0);
    const status = text(selection.state || planning.state || source.status, components.length ? "selected" : "unavailable", 32);
    const overallEvidence = normalizeEvidence(source.workflow_evidence || envelope.workflow_evidence);
    return {
      schema_version: VERSION,
      available: components.length > 0,
      state: status,
      reason_code: text(selection.reason_code || planning.reason_code, "workflow_components_missing", 96),
      template_id: text(selection.workflow_template_id || output.template_id, "", 96),
      template_version: text(selection.workflow_template_version || output.template_version, "", 48),
      component_count: components.length,
      dependency_count: dependencies,
      step_count: steps.length,
      components,
      evidence: overallEvidence,
    };
  }

  const stateLabels = {
    selected: "已选择", matched: "已匹配", clarification: "待澄清", ambiguous: "待选择",
    recoverable: "可恢复", processing: "处理中", completed: "已完成", unavailable: "不可用",
    ready: "可用", degraded: "部分可用", blocked: "已阻断", unknown: "未知",
  };

  function badge(value) {
    const state = text(value, "unknown", 32);
    const tone = ["selected", "matched", "completed", "ready"].includes(state) ? "ready"
      : ["clarification", "ambiguous", "degraded", "recoverable"].includes(state) ? "degraded"
        : ["blocked", "unavailable"].includes(state) ? "unavailable" : "neutral";
    return `<span class="workflow-evidence-badge ${tone}">${escape(stateLabels[state] || state)}</span>`;
  }

  function evidenceRows(evidence) {
    return EVIDENCE_FIELDS.map(field => {
      const item = evidence[field];
      if (!item) return `<span class="workflow-evidence-field"><small>${escape(field)}</small><b>未提供</b></span>`;
      return `<span class="workflow-evidence-field"><small>${escape(field)}</small><b>${badge(item.status)}</b>${item.reason ? `<em>${escape(item.reason)}</em>` : ""}</span>`;
    }).join("");
  }

  function render(data) {
    const model = normalize(data);
    if (!model.available) return "";
    const cards = model.components.map(component => {
      const dependencies = component.depends_on_components.length
        ? component.depends_on_components.join("、") : "无";
      const evidenceKeys = component.evidence_keys.length
        ? `<p class="workflow-evidence-note">声明证据：${escape(component.evidence_keys.join("、"))}</p>` : "";
      const constraints = component.constraint_keys.length
        ? `<p class="workflow-evidence-note">约束字段：${escape(component.constraint_keys.join("、"))}</p>` : "";
      return `<article class="workflow-component-card" data-component-id="${escape(component.component_id)}">`+
        `<div class="workflow-component-head"><strong>${escape(component.component_id)}</strong>${badge(component.evidence.status || model.state)}</div>`+
        `<div class="workflow-component-template">${escape(component.template_id)} · v${escape(component.template_version)}</div>`+
        `<div class="workflow-component-meta"><span>步骤 ${escape(component.step_count)}</span><span>依赖 ${escape(dependencies)}</span></div>`+
        `<div class="workflow-evidence-fields">${evidenceRows(component.evidence)}</div>`+
        evidenceKeys + constraints + `</article>`;
    }).join("");
    const overall = model.evidence.status ? ` · 整体 ${badge(model.evidence.status)}` : "";
    return `<div class="workflow-evidence-block" data-workflow-evidence-state="${escape(cssState(model.state))}">`+
      `<div class="workflow-evidence-summary"><strong>工作流编排</strong>${badge(model.state)}${overall}<span>${model.component_count} 个组件 · ${model.dependency_count} 条组件依赖 · ${model.step_count} 个步骤</span></div>`+
      `<div class="workflow-component-grid">${cards}</div>`+
      `<p class="workflow-evidence-footnote">组件身份和依赖来自结构化 workflow projection；未提供的 evidence 不在前端推断。</p>`+
      `</div>`;
  }

  function renderCompact(data) {
    const model = normalize(data);
    if (!model.available) return "";
    return `<span class="workflow-evidence-compact">${model.component_count} 个组件 · ${model.dependency_count} 条依赖 · ${model.step_count} 个步骤 · ${badge(model.state)}</span>`;
  }

  return Object.freeze({VERSION, normalize, render, renderCompact});
});
