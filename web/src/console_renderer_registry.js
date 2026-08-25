/* Domain-neutral renderer registry for versioned workspace views. */
(function attachConsoleRendererRegistry(root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ConsoleRendererRegistry = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function createModule() {
  const SCHEMA_VERSION = "spatial-agent.console-renderers.v1";
  const COMPOSITE_VIEW_SCHEMA_VERSION = "spatial-agent.composite-view.v1";
  const MAX_RENDERERS = 32;

  const defaultEscape = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
  const record = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);

  function create(options = {}) {
    const escapeHtml = typeof options.escapeHtml === "function" ? options.escapeHtml : defaultEscape;
    const adapters = new Map();
    let generation = 0;

    const genericAdapter = Object.freeze({
      surface: "generic",
      render(context) {
        return {html: renderGenericView(context, escapeHtml), visible: true};
      },
    });
    ["generic", "metrics", "table", "chart"].forEach(id => adapters.set(id, genericAdapter));

    function register(rendererId, adapter) {
      const id = String(rendererId || "").trim().slice(0, 64);
      if (!id || !record(adapter) || typeof adapter.render !== "function") {
        throw new TypeError("renderer adapter requires an id and render function");
      }
      if (!adapters.has(id) && adapters.size >= MAX_RENDERERS) {
        throw new RangeError("renderer registry limit exceeded");
      }
      adapters.set(id, adapter);
      return registry;
    }

    async function renderWorkspace(request = {}) {
      const currentGeneration = ++generation;
      const panels = record(request.panels) ? request.panels : {};
      const specs = normalizeSpecs(request.specs);
      const declared = Array.isArray(request.declaredPanels) ? request.declaredPanels : [];
      const surfaces = record(request.surfaces) ? request.surfaces : {};
      const prefixHtml = String(request.prefixHtml || "");
      const onSurface = typeof request.onSurface === "function" ? request.onSurface : () => {};
      const entries = Object.entries(panels).slice(0, 24);
      const present = new Set(entries.map(([id]) => id));
      declared.slice(0, 24).forEach(id => {
        const bounded = String(id || "").slice(0, 64);
        if (!bounded || present.has(bounded)) return;
        entries.push([bounded, {
          kind: "unavailable",
          title: specs[bounded]?.title || bounded,
          reason: "当前响应没有返回已声明的 view。",
          artifact_available: Boolean(request.run?.artifact_ref),
        }]);
      });

      const usedAdapters = new Set();
      entries.forEach(([id, view]) => {
        const rendererId = String(specs[id]?.renderer || view?.renderer || view?.kind || "generic").slice(0, 64);
        usedAdapters.add(adapters.get(rendererId) || genericAdapter);
      });
      usedAdapters.forEach(adapter => {
        if (typeof adapter.reset === "function") adapter.reset({reason: "render", generation: currentGeneration, surfaces, run: request.run || {}});
      });

      const htmlBySurface = {generic: []};
      const visible = new Set();
      const unknown = [];
      const failures = [];
      for (const [viewId, rawView] of entries) {
        const view = record(rawView) ? rawView : {kind: "unavailable", reason: "view 不是有效对象。"};
        const spec = specs[viewId] || {id: viewId, renderer: view.kind || "generic", title: view.title || viewId};
        const requestedRenderer = String(spec.renderer || view.kind || "generic").slice(0, 64);
        const adapter = adapters.get(requestedRenderer) || genericAdapter;
        const surface = String(adapter.surface || "generic").slice(0, 40);
        if (!adapters.has(requestedRenderer)) unknown.push(requestedRenderer);
        const context = {
          viewId,
          view,
          spec,
          run: request.run || {},
          target: surfaces[surface] || null,
          requestedRenderer,
          fallback: !adapters.has(requestedRenderer),
          isCurrent: () => generation === currentGeneration,
        };
        try {
          const output = await adapter.render(context);
          if (generation !== currentGeneration) return {status: "superseded", schema_version: SCHEMA_VERSION};
          const normalized = normalizeOutput(output);
          if (normalized.html) (htmlBySurface[surface] ||= []).push(normalized.html);
          if (normalized.visible !== false) visible.add(surface);
        } catch (error) {
          failures.push({view_id: viewId, renderer: requestedRenderer});
          const fallback = renderUnavailable(viewId, spec, request.run, escapeHtml);
          (htmlBySurface.generic ||= []).push(fallback);
          visible.add("generic");
        }
      }
      if (generation !== currentGeneration) return {status: "superseded", schema_version: SCHEMA_VERSION};
      if (prefixHtml) {
        htmlBySurface.generic = [prefixHtml].concat(htmlBySurface.generic || []);
        visible.add("generic");
      }
      Object.entries(surfaces).forEach(([surface, target]) => {
        if (!target) return;
        if (surface === "generic") target.innerHTML = (htmlBySurface.generic || []).join("");
        else if ((htmlBySurface[surface] || []).length) target.innerHTML = htmlBySurface[surface].join("");
        onSurface(surface, visible.has(surface));
      });
      return {
        status: failures.length ? "degraded" : "rendered",
        schema_version: SCHEMA_VERSION,
        rendered_surfaces: [...visible],
        unknown_renderers: [...new Set(unknown)].slice(0, 8),
        failures: failures.slice(0, 8),
      };
    }

    function reset(context = {}) {
      generation += 1;
      const resetContext = {
        reason: boundedReason(context.reason, "reset"),
        generation: Number.isFinite(Number(context.generation)) ? Number(context.generation) : generation,
        surfaces: record(context.surfaces) ? context.surfaces : {},
        run: record(context.run) ? context.run : {},
      };
      new Set(adapters.values()).forEach(adapter => {
        if (typeof adapter.reset === "function") adapter.reset(resetContext);
      });
    }

    function context() {
      const output = {};
      new Set(adapters.values()).forEach(adapter => {
        if (typeof adapter.context !== "function") return;
        const value = adapter.context();
        if (record(value)) Object.assign(output, value);
      });
      return output;
    }

    const registry = Object.freeze({register, renderWorkspace, reset, context, projectionToPanels});
    return registry;
  }

  function projectionToPanels(projection) {
    if (!record(projection) || projection.schema_version !== COMPOSITE_VIEW_SCHEMA_VERSION) return null;
    const panels = {};
    const specs = [];
    const declaredPanels = [];
    (Array.isArray(projection.views) ? projection.views : []).slice(0, 24).forEach((view, index) => {
      if (!record(view)) return;
      const id = String(view.view_id || "view-" + (index + 1)).trim().slice(0, 64);
      if (!id || panels[id]) return;
      const payload = record(view.payload) ? Object.assign({}, view.payload) : {};
      const kind = String(view.kind || payload.kind || "generic").slice(0, 64);
      const renderer = String(view.renderer || payload.renderer || (kind === "comparison_chart" ? "chart" : kind)).slice(0, 64);
      panels[id] = Object.assign(payload, {
        view_id: id,
        kind,
        renderer,
        title: String(view.title || payload.title || id).slice(0, 160),
        state: String(view.state || payload.state || projection.state || "unknown").slice(0, 32),
        component_id: view.component_id || payload.component_id || null,
        domain_id: view.domain_id || payload.domain_id || null,
      });
      specs.push({id, renderer, title: panels[id].title});
      declaredPanels.push(id);
    });
    if (!declaredPanels.length) {
      panels.generic = {
        kind: "unavailable",
        title: "组合分析结果",
        reason: "本次响应没有可展示的结构化 view。",
        artifact_available: Array.isArray(projection.artifacts) && projection.artifacts.length > 0,
      };
      specs.push({id: "generic", renderer: "generic", title: "组合分析结果"});
      declaredPanels.push("generic");
    }
    return {panels, specs, declaredPanels};
  }

  function normalizeSpecs(raw) {
    const output = {};
    const values = Array.isArray(raw) ? raw : Object.values(record(raw) ? raw : {});
    values.slice(0, 24).forEach(spec => {
      if (!record(spec) || !spec.id) return;
      const id = String(spec.id).slice(0, 64);
      output[id] = {
        id,
        renderer: String(spec.renderer || "generic").slice(0, 64),
        title: String(spec.title || id).slice(0, 160),
      };
    });
    return output;
  }

  function normalizeOutput(value) {
    if (typeof value === "string") return {html: value, visible: Boolean(value)};
    if (!record(value)) return {html: "", visible: value !== false};
    return {html: typeof value.html === "string" ? value.html : "", visible: value.visible !== false};
  }

  function boundedReason(value, fallback) {
    const reason = typeof value === "string" ? value.trim().slice(0, 48) : "";
    return reason || fallback;
  }

  function renderGenericView(context, escapeHtml) {
    const {viewId, view, spec, run, requestedRenderer, fallback} = context;
    const title = escapeHtml(view.title || spec.title || viewId);
    const renderer = escapeHtml(requestedRenderer || view.kind || "generic");
    if (view.kind === "unavailable") return renderUnavailable(viewId, spec, run, escapeHtml, view.reason, view.artifact_available);
    const chart = requestedRenderer === "chart" ? renderChart(view, escapeHtml) : "";
    const distribution = renderDistribution(view.distribution, escapeHtml);
    const rows = (Array.isArray(view.rows) ? view.rows : []).slice(0, 40).map(row => {
      const item = record(row) ? row : {value: row};
      const label = item.label ?? item.dataset ?? item.name ?? item.id ?? "字段";
      const raw = item.value ?? item.status_label ?? item.status ?? item.count ?? item.detail;
      const value = raw === undefined ? renderBoundedValue(item, escapeHtml) : renderReadableValue(raw, escapeHtml);
      return '<div class="view-row"><small>' + escapeHtml(label) + '</small><b>' + value + '</b></div>';
    }).join("");
    const table = renderTable(view.table, escapeHtml);
    const metrics = renderMetrics(view.metrics, escapeHtml);
    const error = view.error ? '<div class="error">' + escapeHtml(view.error) + '</div>' : "";
    const note = view.note ? '<div class="distribution-note">' + escapeHtml(view.note) + '</div>' : "";
    const fields = renderObjectFields(view, escapeHtml);
    const fallbackNote = fallback
      ? '<div class="distribution-note">renderer ' + renderer + ' 未注册，已使用通用有界展示。</div>'
      : "";
    const hasChart = Boolean(chart && chart.replace(/<[^>]+>/g, "").trim());
    const empty = !metrics && !rows && !table && !error && !note && !fields && !distribution && !hasChart
      ? '<div class="distribution-note">当前 view 没有可读展示字段，已显示有界空态。</div>' : "";
    return '<section class="structured-view-block"><div class="stat-context"><strong>' + title + '</strong><span>' + renderer + '</span></div>'
      + fallbackNote + error + (metrics ? '<div class="metric-grid">' + metrics + '</div>' : "")
      + (rows ? '<div class="view-rows">' + rows + '</div>' : "") + table + chart + distribution + fields + note + empty + '</section>';
  }

  function renderUnavailable(viewId, spec, run, escapeHtml, reason, artifactAvailable) {
    const title = escapeHtml(spec?.title || viewId || "结构化结果");
    const ref = artifactName(run?.artifact_ref || "");
    const link = ref ? '<a href="/artifacts/runs/' + encodeURIComponent(ref) + '" target="_blank">打开运行 artifact</a>' : "";
    return '<section class="structured-view-block"><div class="stat-context"><strong>' + title + '</strong><span>unavailable</span></div><div class="distribution-note">'
      + escapeHtml(reason || "当前没有可用视图数据。") + (artifactAvailable ? " · 已保留可恢复 artifact。" : "") + (link ? " · " + link : "") + '</div></section>';
  }

  function renderBoundedValue(value, escapeHtml) {
    return renderReadableValue(value, escapeHtml, 8);
  }

  function renderReadableValue(value, escapeHtml, limit = 8) {
    if (Array.isArray(value)) return value.slice(0, limit).map(item => renderReadableValue(item, escapeHtml, 5)).join("；");
    if (record(value)) return Object.entries(value).slice(0, limit).map(([key, item]) => escapeHtml(key) + ": " + renderReadableValue(item, escapeHtml, 5)).join("，");
    return escapeHtml(formatScalarValue(value));
  }

  function formatScalarValue(value) {
    if (value === null || value === undefined || value === "") return "-";
    if (typeof value === "boolean") return value ? "是" : "否";
    if (typeof value === "number" && Number.isFinite(value)) return formatNumberValue(value);
    const text = String(value);
    const match = text.match(/^\s*(-?(?:\d+\.?\d*|\.\d+))(\s*(?:%|°|米|公里|个|条|类|像元))\s*$/);
    if (match) return formatNumberValue(Number(match[1])) + match[2];
    return text;
  }

  function formatNumberValue(value) {
    if (!Number.isFinite(value)) return "-";
    if (Math.abs(value) >= 100000000) {
      return (value / 100000000).toLocaleString("zh-CN", {maximumFractionDigits: 2}) + "亿";
    }
    return value.toLocaleString("zh-CN", {maximumFractionDigits: 3});
  }

  function renderObjectFields(view, escapeHtml) {
    const reserved = new Set(["schema_version", "view_schema_version", "kind", "title", "subtitle", "note", "error", "metrics", "rows", "table", "series", "encodings", "distribution"]);
    const fields = Object.entries(view || {}).filter(([key, value]) => !reserved.has(key) && value !== null && value !== undefined).slice(0, 8);
    if (!fields.length) return "";
    return '<div class="view-rows">' + fields.map(([key, value]) => '<div class="view-row"><small>' + escapeHtml(key) + '</small><b>' + renderBoundedValue(value, escapeHtml) + '</b></div>').join("") + '</div>';
  }

  function renderMetrics(metrics, escapeHtml) {
    return (Array.isArray(metrics) ? metrics : []).slice(0, 24).map(item => '<div class="metric"><b>' + renderReadableValue(item?.value, escapeHtml) + '</b><small>' + escapeHtml(item?.label || "指标") + '</small></div>').join("");
  }

  function renderTable(table, escapeHtml) {
    if (!record(table) || !Array.isArray(table.rows) || !table.rows.length) return "";
    const columns = Array.isArray(table.columns) ? table.columns.slice(0, 16) : [];
    return '<table class="view-table"><thead><tr>' + columns.map(col => '<th>' + escapeHtml(col) + '</th>').join("") + '</tr></thead><tbody>'
      + table.rows.slice(0, 40).map(row => '<tr>' + (Array.isArray(row) ? row : [row]).slice(0, 16).map(cell => '<td>' + renderReadableValue(cell, escapeHtml) + '</td>').join("") + '</tr>').join("") + '</tbody></table>';
  }

  function renderDistribution(distribution, escapeHtml) {
    if (!record(distribution) || !Array.isArray(distribution.bins) || !distribution.bins.length) return "";
    const sampleCount = Number(distribution.sample_count);
    const bins = distribution.bins.slice(0, 12).map((bin, index) => {
      const item = record(bin) ? bin : {value: bin};
      const count = Number(item.count ?? item.frequency ?? item.value ?? 0);
      const lower = item.lower ?? item.min ?? item.start;
      const upper = item.upper ?? item.max ?? item.end;
      const label = item.label ?? (lower !== undefined || upper !== undefined
        ? formatScalarValue(lower) + "–" + formatScalarValue(upper)
        : "区间 " + (index + 1));
      const ratio = Number(item.share ?? item.ratio);
      const share = Number.isFinite(ratio) ? ratio : (sampleCount > 0 && Number.isFinite(count) ? count / sampleCount : 0);
      const width = Math.max(2, Math.min(100, share * 100));
      const shareText = Number.isFinite(share) && share > 0 ? "（" + (share * 100).toLocaleString("zh-CN", {maximumFractionDigits: 1}) + "%）" : "";
      return '<div class="distribution-row"><div class="distribution-row-head"><span>' + escapeHtml(label) + '</span><b>' + escapeHtml(formatScalarValue(count)) + ' 个' + escapeHtml(shareText) + '</b></div><div class="distribution-track"><i class="distribution-fill" style="width:' + width + '%"></i></div></div>';
    }).join("");
    return '<section class="distribution-block" aria-label="数值分布"><div class="distribution-summary"><strong>区间分布</strong><span>样本数量：' + escapeHtml(formatScalarValue(distribution.sample_count)) + '</span></div><div class="distribution-list">' + bins + '</div></section>';
  }

  function renderChart(view, escapeHtml) {
    if (view?.kind !== "comparison_chart") return "";
    const points = (((view.series || [])[0] || {}).points || []).filter(Boolean).slice(0, 40);
    const max = Math.max(1, ...points.filter(point => point.y !== null && point.y !== undefined).map(point => Number(point.y) || 0));
    const axis = (view.encodings || {}).y || {};
    const chart = points.length ? '<div class="chart-view">' + points.map(point => {
      const width = point.y === null || point.y === undefined ? 0 : Math.max(2, Math.min(100, (Number(point.y) || 0) / max * 100));
      const detail = point.run_id ? ' <button type="button" class="compare-detail" data-run-id="' + escapeHtml(point.run_id) + '">详情</button>' : "";
      return '<div class="chart-row"><span class="chart-row-label">' + escapeHtml(point.label ?? point.x ?? "-") + '</span><div class="chart-track"><i class="chart-fill" style="width:' + width + '%"></i></div><span class="chart-value">' + escapeHtml(formatChartValue(point.y, axis.label)) + detail + '</span></div>';
    }).join("") + '</div>' : "";
    return '<div class="stat-context"><strong>' + escapeHtml(view.title || "对比图") + '</strong><span>' + escapeHtml(view.comparison_kind || view.chart_type || "chart") + '</span></div><div class="metric-grid">'
      + renderMetrics(view.metrics, escapeHtml) + '</div>' + chart + renderTable(view.table, escapeHtml) + (view.note ? '<div class="distribution-note">' + escapeHtml(view.note) + '</div>' : "");
  }

  function formatChartValue(value, label) {
    const text = formatScalarValue(value);
    return label ? text + " " + label : text;
  }

  function artifactName(ref) {
    const parts = String(ref || "").split(/[\\/]/);
    return parts[parts.length - 1] || "";
  }

  return Object.freeze({SCHEMA_VERSION, COMPOSITE_VIEW_SCHEMA_VERSION, create, projectionToPanels});
});
