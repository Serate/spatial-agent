/*
 * Domain-neutral Evidence Registry projection for the Console.
 *
 * The backend owns the registry and selection schemas. This module only
 * renders their bounded public projection, so Text, GIS, and future Domains
 * share the same evidence surface.
 */
(function attachEvidenceRegistry(global) {
  const REGISTRY_SCHEMA = 'spatial-agent.evidence-registry.v1';
  const MAX_ENTRIES = 16;
  const MAX_TEXT = 160;
  const labels = {
    workflow_selection: '工作流选择',
    planner_selection: '规划器选择',
    result: '结果契约',
    plan_quality: '计划质量',
    execution_timeline: '执行时间线',
    action_lifecycle: '动作生命周期',
    replanning: '计划修复'
  };
  const stateLabels = {
    selected: '已选择', matched: '已匹配', mismatch: '不一致',
    ambiguous: '待选择', clarification: '待澄清', unavailable: '不可用',
    ready: '可用', available: '可用', complete: '完整', incomplete: '不完整', unknown: '未知'
  };

  function record(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }
  function text(value, fallback = '', limit = MAX_TEXT) {
    const valueText = value === null || value === undefined ? '' : String(value).trim();
    return (valueText || fallback).slice(0, limit);
  }
  function list(value, limit = MAX_ENTRIES) {
    return (Array.isArray(value) ? value : []).map(item => text(item)).filter(Boolean)
      .filter((item, index, items) => items.indexOf(item) === index).slice(0, limit);
  }
  function escape(value) {
    return String(value ?? '').replace(/[&<>"']/g, character => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[character]));
  }
  function normalizeRegistry(value) {
    if (!record(value) || value.schema_version !== REGISTRY_SCHEMA || !Array.isArray(value.entries)) {
      return {schema_version: REGISTRY_SCHEMA, available: false, entry_count: 0, entries: [],
        reason_code: record(value) && value.schema_version ? 'evidence_registry_unknown_schema' : 'evidence_registry_missing'};
    }
    const entries = value.entries.slice(0, MAX_ENTRIES).map(item => {
      if (!record(item)) return null;
      const id = text(item.id, '', 96);
      const schemaVersion = text(item.schema_version, '', 96);
      const reference = text(item.reference, '', 160);
      if (!id || !schemaVersion || !reference) return null;
      return {id, schema_version: schemaVersion, available: item.available === true,
        state: text(item.state, 'unknown', 48), reference,
        count: Number.isInteger(item.count) ? Math.max(0, Math.min(item.count, 128)) : null};
    }).filter(Boolean);
    return {schema_version: REGISTRY_SCHEMA, available: value.available === true,
      entry_count: entries.length, entries, reason_code: text(value.reason_code, '')};
  }
  function normalizeSelection(planning, registry) {
    const source = record(planning) ? planning : {};
    const normalizedRegistry = normalizeRegistry(registry);
    const entries = Object.fromEntries(normalizedRegistry.entries.map(item => [item.id, item]));
    const workflow = record(source.workflow_selection) ? source.workflow_selection : {};
    const planner = record(source.planner_selection) ? source.planner_selection : {};
    return {
      registry: normalizedRegistry, entries,
      workflow: {schema_version: text(workflow.schema_version, ''),
        state: text(workflow.state, entries.workflow_selection?.state || 'unavailable', 48),
        reason_code: text(workflow.reason_code, 'selection_unavailable'), source: text(workflow.source, 'unknown', 64),
        selected_capability_id: text(workflow.selected_capability_id, '', 96), candidate_ids: list(workflow.candidate_ids, 8),
        candidate_count: Number.isInteger(workflow.candidate_count) ? workflow.candidate_count : null},
      planner: {schema_version: text(planner.schema_version, ''),
        state: text(planner.state, entries.planner_selection?.state || 'unavailable', 48),
        reason_code: text(planner.reason_code, 'planner_selection_unavailable'), planner_kind: text(planner.planner_kind, 'unknown', 96),
        result_type: text(planner.result_type, '', 96), selected_capability_id: text(planner.selected_capability_id, '', 96),
        planner_capability_id: text(planner.planner_capability_id, '', 96), candidate_ids: list(planner.candidate_ids, 8)}
    };
  }
  function stateLabel(state) { return stateLabels[state] || stateLabels.unknown; }
  function badge(state) {
    const className = ['ready', 'passed', 'selected', 'matched'].includes(state) ? 'ready'
      : ['degraded', 'warning', 'ambiguous', 'clarification', 'mismatch'].includes(state) ? 'degraded'
        : ['unavailable', 'incomplete'].includes(state) ? 'unavailable' : 'neutral';
    return '<span class="evidence-status ' + className + '">' + escape(stateLabel(state)) + '</span>';
  }
  function detailRows(model) {
    const rows = [];
    if (model.selected_capability_id) rows.push('能力：' + model.selected_capability_id);
    if (model.planner_capability_id) rows.push('计划能力：' + model.planner_capability_id);
    if (model.result_type) rows.push('结果类型：' + model.result_type);
    if (model.source) rows.push('来源：' + model.source);
    if (model.planner_kind) rows.push('规划器：' + model.planner_kind);
    if (model.candidate_ids.length) rows.push('候选：' + model.candidate_ids.join('、'));
    if (model.candidate_count !== null && !model.candidate_ids.length) rows.push('候选数：' + model.candidate_count);
    return rows.slice(0, 6);
  }
  function renderCard(title, model, entry) {
    const state = model.state || entry?.state || 'unavailable';
    const schema = model.schema_version || entry?.schema_version || '未提供 schema';
    const details = detailRows(model).map(item => '<li>' + escape(item) + '</li>').join('');
    return '<article class="selection-evidence-card ' + escape(state) + '">' +
      '<div class="selection-evidence-title"><strong>' + escape(title) + '</strong>' + badge(state) + '</div>' +
      '<p>' + escape(model.reason_code || '未提供原因') + '</p>' +
      (details ? '<ul class="evidence-list">' + details + '</ul>' : '') +
      '<small>schema ' + escape(schema) + (entry?.reference ? ' · 引用 ' + escape(entry.reference) : '') + '</small></article>';
  }
  function render(planning, registry) {
    const model = normalizeSelection(planning, registry);
    const entries = model.registry.entries;
    const registryState = model.registry.available ? 'ready' : 'unavailable';
    const entryRows = entries.map(item => '<li><strong>' + escape(labels[item.id] || item.id) + '</strong> ' +
      badge(item.state) + ' · ' + escape(item.schema_version) + ' · ' + escape(item.reference) +
      (item.count === null ? '' : ' · ' + escape(item.count) + ' 项') + '</li>').join('');
    return '<div class="selection-evidence-block" data-evidence-registry-state="' + escape(registryState) + '">' +
      '<div class="selection-evidence-summary"><strong>Evidence Registry</strong> ' + badge(registryState) +
      '<span>' + escape(model.registry.available ? (model.registry.entry_count + ' 个版本化入口') : (model.registry.reason_code || '证据索引不可用')) + '</span></div>' +
      '<div class="selection-evidence-grid">' + renderCard('工作流选择', model.workflow, model.entries.workflow_selection) +
      renderCard('规划器选择', model.planner, model.entries.planner_selection) + '</div>' +
      (entryRows ? '<details class="selection-evidence-entries"><summary>查看全部证据入口</summary><ul class="evidence-list">' + entryRows + '</ul></details>' :
        '<div class="evidence-empty">当前没有可读取的版本化证据入口。</div>') + '</div>';
  }
  function renderCompact(planning, registry) {
    const model = normalizeSelection(planning, registry);
    return '<span class="selection-evidence-compact">选择证据：工作流 ' + badge(model.workflow.state) +
      ' · 规划器 ' + badge(model.planner.state) + (model.planner.result_type ? ' · ' + escape(model.planner.result_type) : '') + '</span>';
  }
  global.ConsoleEvidenceRegistry = Object.freeze({REGISTRY_SCHEMA, normalizeRegistry, normalizeSelection, render, renderCompact});
})(window);
