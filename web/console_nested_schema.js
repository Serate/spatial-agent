/*
 * Bounded Console-side compatibility seam for nested result contracts.
 *
 * The server remains the authority for result/workspace/view semantics.  This
 * module only protects the renderer from old, partial, or future payloads:
 * missing schema versions are treated as legacy-compatible, while unknown
 * versions and malformed nested objects become bounded unavailable panels.
 * It deliberately has no DOM or GIS dependency so the same checks can run in
 * the Node static smoke profile.
 */
(function attachConsoleNestedSchema(root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ConsoleNestedSchema = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function createConsoleNestedSchema() {
  const VERSIONS = Object.freeze({
    result: "spatial-agent.result-envelope.v1",
    workspace: "spatial-agent.workspace.v1",
    views: "spatial-agent.views.v1",
    view: "spatial-agent.view.v1",
    dataProfile: "spatial-agent.data-profile.v1",
    // The shared contract uses spatial-agent.view.v1 for both view specs and
    // concrete panel models; keep the alias explicit in the Console seam.
    panel: "spatial-agent.view.v1",
  });
  const LIMITS = Object.freeze({
    id: 80,
    title: 160,
    reason: 320,
    panels: 24,
    specs: 24,
    issues: 8,
  });
  const DATA_KINDS = new Set([
    "unknown", "text", "vector", "raster", "metrics", "timeseries",
    "document_evidence", "composite",
  ]);

  function isRecord(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function boundedText(value, fallback, limit) {
    const text = typeof value === "string" ? value.trim() : "";
    if (!text) return fallback;
    return text.slice(0, limit);
  }

  function issue(issues, path, code) {
    if (issues.length >= LIMITS.issues) return;
    issues.push({path: path.slice(0, LIMITS.id), code: code.slice(0, LIMITS.id)});
  }

  function checkVersion(raw, expected, path, issues) {
    // Artifacts produced before nested versions were introduced remain
    // readable.  A non-empty unknown version must never be silently parsed as
    // the current schema.
    if (raw === undefined || raw === null || raw === "") return expected;
    if (typeof raw !== "string" || raw !== expected) {
      issue(issues, path, "unknown_schema_version");
      return null;
    }
    return expected;
  }

  function fallbackPanel(id, reason, artifactAvailable) {
    return {
      schema_version: VERSIONS.panel,
      kind: "unavailable",
      title: boundedText(id, "结构化结果", LIMITS.title),
      reason: boundedText(reason, "当前结果视图不可用。", LIMITS.reason),
      artifact_available: artifactAvailable === true,
    };
  }

  function fallbackWorkspace(resultType, reason, issues) {
    return {
      schema_version: VERSIONS.workspace,
      registered_type: boundedText(resultType, "unknown", LIMITS.id),
      primary_panel: "generic",
      common_panels: [],
      panels: ["generic"],
      view_specs: [{
        id: "generic",
        renderer: "generic",
        title: "结构化结果",
        schema_version: VERSIONS.view,
      }],
      state: "unavailable",
      unavailable_reason: boundedText(reason, "结果工作区契约不可用。", LIMITS.reason),
      _issues: issues.slice(0, LIMITS.issues),
    };
  }

  function fallbackViews(reason, artifactAvailable) {
    return {
      schema_version: VERSIONS.views,
      panels: {
        generic: fallbackPanel("结构化结果", reason, artifactAvailable),
      },
      state: "unavailable",
    };
  }

  function normalizeDataProfile(raw, issues) {
    if (raw === undefined || raw === null) {
      return {
        schema_version: VERSIONS.dataProfile,
        primary: "unknown",
        kinds: ["unknown"],
      };
    }
    if (!isRecord(raw)) {
      issue(issues, "result.data_profile", "data_profile_not_object");
      return {schema_version: VERSIONS.dataProfile, primary: "unknown", kinds: ["unknown"]};
    }
    const version = checkVersion(raw.schema_version, VERSIONS.dataProfile, "result.data_profile.schema_version", issues);
    const rawKinds = Array.isArray(raw.kinds) ? raw.kinds.slice(0, 8) : [];
    const validKinds = rawKinds.every(kind => typeof kind === "string" && DATA_KINDS.has(kind));
    const kinds = [...new Set(rawKinds)];
    if (!version || !validKinds || !kinds.length) {
      issue(issues, "result.data_profile.kinds", "data_profile_kinds_invalid");
      return {schema_version: VERSIONS.dataProfile, primary: "unknown", kinds: ["unknown"]};
    }
    const primary = typeof raw.primary === "string" && kinds.includes(raw.primary) ? raw.primary : kinds[0];
    return {schema_version: version, primary, kinds};
  }

  function normalizePanel(id, raw, issues, artifactAvailable) {
    const path = "result.views.panels." + id;
    if (!isRecord(raw)) {
      issue(issues, path, "panel_not_object");
      return fallbackPanel(id, "该结果面板不是有效对象，已切换为不可用空态。", artifactAvailable);
    }
    const version = checkVersion(raw.schema_version, VERSIONS.panel, path + ".schema_version", issues);
    if (!version) {
      return fallbackPanel(id, "该结果面板使用了未知版本，暂时无法安全展示。", artifactAvailable);
    }
    const viewVersion = checkVersion(raw.view_schema_version, VERSIONS.view, path + ".view_schema_version", issues);
    if (!viewVersion) {
      return fallbackPanel(id, "该结果视图使用了未知版本，暂时无法安全展示。", artifactAvailable);
    }
    // Keep the existing view model fields for the domain-owned renderers.  The
    // object itself is bounded by the server contract; only presentation
    // strings are clipped again at this trust boundary.
    if (typeof raw.kind !== "string" || !raw.kind.trim()) {
      issue(issues, path + ".kind", "panel_kind_missing");
      return fallbackPanel(id, "该结果面板缺少可识别类型，暂时无法安全展示。", artifactAvailable);
    }
    const panel = Object.assign({}, raw, {schema_version: version});
    if (typeof panel.title === "string") panel.title = panel.title.slice(0, LIMITS.title);
    if (typeof panel.reason === "string") panel.reason = panel.reason.slice(0, LIMITS.reason);
    if (typeof panel.note === "string") panel.note = panel.note.slice(0, LIMITS.reason);
    if (typeof panel.error === "string") panel.error = panel.error.slice(0, LIMITS.reason);
    return panel;
  }

  function normalizeWorkspace(raw, resultType, issues) {
    if (raw === undefined || raw === null) {
      return {
        value: {
          schema_version: VERSIONS.workspace,
          registered_type: boundedText(resultType, "unknown", LIMITS.id),
          panels: [],
          common_panels: [],
          view_specs: [],
          state: "legacy",
        },
        invalid: false,
      };
    }
    if (!isRecord(raw)) {
      issue(issues, "result.workspace", "workspace_not_object");
      return {value: fallbackWorkspace(resultType, "结果工作区不是有效对象，已切换为不可用空态。", issues), invalid: true};
    }
    const version = checkVersion(raw.schema_version, VERSIONS.workspace, "result.workspace.schema_version", issues);
    const panels = raw.panels;
    const commonPanels = raw.common_panels;
    const specs = raw.view_specs;
    if (!version || (panels !== undefined && (!Array.isArray(panels) || panels.some(item => typeof item !== "string")))) {
      issue(issues, "result.workspace.panels", "panels_not_string_list");
      return {value: fallbackWorkspace(resultType, "结果工作区面板声明无效，已切换为不可用空态。", issues), invalid: true};
    }
    if (commonPanels !== undefined && (!Array.isArray(commonPanels) || commonPanels.some(item => typeof item !== "string"))) {
      issue(issues, "result.workspace.common_panels", "common_panels_not_string_list");
      return {value: fallbackWorkspace(resultType, "结果工作区公共面板声明无效，已切换为不可用空态。", issues), invalid: true};
    }
    if (specs !== undefined && (!Array.isArray(specs) || specs.length > LIMITS.specs)) {
      issue(issues, "result.workspace.view_specs", "view_specs_invalid");
      return {value: fallbackWorkspace(resultType, "结果工作区 view spec 无效，已切换为不可用空态。", issues), invalid: true};
    }
    const normalizedSpecs = (Array.isArray(specs) ? specs : []).map((spec, index) => {
      if (!isRecord(spec) || typeof spec.id !== "string") {
        issue(issues, "result.workspace.view_specs." + index, "view_spec_invalid");
        return null;
      }
      const specVersion = checkVersion(spec.schema_version, VERSIONS.view, "result.workspace.view_specs." + index + ".schema_version", issues);
      if (!specVersion) return null;
      return {
        id: spec.id.slice(0, LIMITS.id),
        renderer: boundedText(spec.renderer, "generic", LIMITS.id),
        title: boundedText(spec.title, spec.id, LIMITS.title),
        schema_version: specVersion,
      };
    });
    if (normalizedSpecs.some(item => !item)) {
      return {value: fallbackWorkspace(resultType, "结果工作区包含未知或无效 view spec，已切换为不可用空态。", issues), invalid: true};
    }
    return {
      value: Object.assign({}, raw, {
        schema_version: version,
        registered_type: boundedText(raw.registered_type, resultType || "unknown", LIMITS.id),
        panels: (Array.isArray(panels) ? panels : []).slice(0, LIMITS.panels).map(item => item.slice(0, LIMITS.id)),
        common_panels: (Array.isArray(commonPanels) ? commonPanels : []).slice(0, LIMITS.panels).map(item => item.slice(0, LIMITS.id)),
        view_specs: normalizedSpecs,
      }),
      invalid: false,
    };
  }

  function normalizeViews(raw, workspace, issues, artifactAvailable) {
    if (raw === undefined || raw === null) {
      return {value: {schema_version: VERSIONS.views, panels: {}, state: "legacy"}, invalid: false};
    }
    if (!isRecord(raw)) {
      issue(issues, "result.views", "views_not_object");
      return {value: fallbackViews("结果视图不是有效对象，已切换为不可用空态。", artifactAvailable), invalid: true};
    }
    const version = checkVersion(raw.schema_version, VERSIONS.views, "result.views.schema_version", issues);
    const sourcePanels = raw.panels;
    if (!version || !isRecord(sourcePanels)) {
      issue(issues, "result.views.panels", "view_panels_not_object");
      return {value: fallbackViews("结果视图面板结构无效，已切换为不可用空态。", artifactAvailable), invalid: true};
    }
    const panels = {};
    const ids = Object.keys(sourcePanels).slice(0, LIMITS.panels);
    ids.forEach(id => { panels[id.slice(0, LIMITS.id)] = normalizePanel(id, sourcePanels[id], issues, artifactAvailable); });
    return {value: Object.assign({}, raw, {schema_version: version, panels}), invalid: false};
  }

  function normalize(input) {
    const data = isRecord(input) ? input : {};
    const issues = [];
    const hasResultField = Object.prototype.hasOwnProperty.call(data, "result");
    const hasResultObject = isRecord(data.result);
    if (hasResultField && !hasResultObject) issue(issues, "result", "result_not_object");
    const rawResult = hasResultObject ? data.result : {
      type: data.result_type || data.plan?.output?.type || "unknown",
      workspace: data.workspace,
      views: data.views,
    };
    const rootVersion = checkVersion(rawResult.schema_version, VERSIONS.result, "result.schema_version", issues);
    const resultType = boundedText(rawResult.type || rawResult.result_type || data.result_type, "unknown", LIMITS.id);
    const dataProfile = normalizeDataProfile(rawResult.data_profile, issues);
    const workspaceResult = normalizeWorkspace(rawResult.workspace, resultType, issues);
    const viewsResult = normalizeViews(rawResult.views, workspaceResult.value, issues, Boolean(data.artifact_ref));
    const invalid = !rootVersion || workspaceResult.invalid || viewsResult.invalid || (hasResultField && !hasResultObject);
    const result = Object.assign({}, rawResult, {
      schema_version: rootVersion || VERSIONS.result,
      type: resultType,
      data_profile: dataProfile,
      workspace: workspaceResult.value,
      views: viewsResult.value,
    });
    const hasUnavailablePanel = Object.values(result.views.panels || {}).some(
      panel => panel && panel.kind === "unavailable"
    );
    if (hasUnavailablePanel && !result.views.panels.generic) {
      result.views.panels.generic = fallbackPanel(
        "结构化结果",
        "至少一个嵌套结果面板不可安全展示，已提供有界空态。",
        Boolean(data.artifact_ref)
      );
    }
    if (invalid) {
      const reason = "结果包含未知或无效的嵌套契约，已切换为有界不可用空态。";
      result.workspace = fallbackWorkspace(resultType, reason, issues);
      result.views = fallbackViews(reason, Boolean(data.artifact_ref));
      result.views.panels.generic = fallbackPanel("结构化结果", reason, Boolean(data.artifact_ref));
    }
    const safeData = Object.assign({}, data, {result});
    return {
      data: safeData,
      result,
      workspace: result.workspace,
      views: result.views,
      issues: issues.slice(0, LIMITS.issues),
      invalid,
      hasUnavailablePanel,
      reason: invalid ? "结果包含未知或无效的嵌套契约，已切换为有界不可用空态。" : "",
    };
  }

  return Object.freeze({VERSIONS, LIMITS, normalize, fallbackPanel});
});
