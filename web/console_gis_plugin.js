/* GIS renderer adapter. Domain-specific geometry semantics stay in this file. */
(function attachConsoleGisPlugin(root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ConsoleGisPlugin = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function createModule() {
  const SCHEMA_VERSION = "spatial-agent.console-gis-plugin.v1";
  const defaultEscape = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);

  function createMapAdapter(options = {}) {
    const escapeHtml = typeof options.escapeHtml === "function" ? options.escapeHtml : defaultEscape;
    const fetchJson = typeof options.fetchJson === "function" ? options.fetchJson : async path => {
      const response = await fetch(path);
      if (!response.ok) throw new Error("GeoJSON 下载失败（HTTP " + response.status + "）");
      return response.json();
    };
    const leaflet = () => options.leaflet || (typeof globalThis !== "undefined" ? globalThis.L : null);
    const selectionTarget = () => typeof options.selectionTarget === "function" ? options.selectionTarget() : options.selectionTarget;
    const useSelectionButton = () => typeof options.useSelectionButton === "function" ? options.useSelectionButton() : options.useSelectionButton;
    let map = null;
    let selected = {};

    function destroyMap() {
      if (map && typeof map.remove === "function") map.remove();
      map = null;
    }

    function reset() {
      destroyMap();
      selected = {};
      const label = selectionTarget();
      const button = useSelectionButton();
      if (label) label.textContent = "点击可视化要素后，可将其作为下一次请求的领域上下文。";
      if (button) button.disabled = true;
    }

    function context() {
      return selected.admin_name ? {spatial_context: Object.assign({}, selected)} : {};
    }

    const selectionButton = useSelectionButton();
    if (selectionButton && selectionButton.dataset.rendererSelectionBound !== "true") {
      selectionButton.dataset.rendererSelectionBound = "true";
      selectionButton.addEventListener("click", () => {
        if (selected.admin_name && typeof options.onUseSelection === "function") {
          options.onUseSelection(Object.assign({}, selected));
        }
      });
    }

    function selectFeature(feature) {
      const props = feature?.properties || {};
      const adminName = props.name || props.admin_name || props.area_name || "";
      selected = {
        admin_name: adminName,
        source: props.geometry_source || "map",
        crs: props.geometry_crs || "",
        geometry_type: feature?.geometry?.type || "",
        geometry_available: Boolean(feature?.geometry),
      };
      const label = selectionTarget();
      const button = useSelectionButton();
      if (label) label.textContent = adminName ? "已选中：" + adminName + " · " + (selected.crs || "未知 CRS") : "已选中空间要素，但缺少可绑定的区域名称。";
      if (button) button.disabled = !adminName;
      if (typeof options.onSelection === "function") options.onSelection(Object.assign({}, selected));
    }

    async function render(contextValue) {
      const view = contextValue.view || {};
      const target = contextValue.target;
      if (!target) return {visible: false};
      if (view.mode === "raster_bounds") {
        renderRasterBounds(target, view, escapeHtml);
        return {visible: true};
      }
      if (view.mode !== "geojson") {
        target.innerHTML = '<div class="map-empty">当前 renderer 没有收到可绘制几何。</div>';
        return {visible: true};
      }
      try {
        const geojson = view.geojson || await fetchJson(artifactPath(contextValue.run, view));
        if (!contextValue.isCurrent()) return {visible: false};
        renderGeoJSON(target, geojson, {leaflet: leaflet(), escapeHtml, destroyMap, setMap: value => { map = value; }, selectFeature});
      } catch (error) {
        if (!contextValue.isCurrent()) return {visible: false};
        destroyMap();
        target.innerHTML = '<div class="map-empty">空间预览加载失败：' + escapeHtml(error?.message || "未知错误") + '</div>';
      }
      return {visible: true};
    }

    return Object.freeze({surface: "visual", render, reset, context});
  }

  function artifactPath(run, view) {
    const envelope = run?.result || {};
    const reference = envelope.geometry?.reference || envelope.artifacts?.geometry || {};
    const direct = reference?.access?.path;
    if (typeof direct === "string" && direct.startsWith("/artifacts/geojson/")) return direct;
    const ref = reference?.ref || run?.geojson_ref || view?.geojson_ref || "";
    const name = String(ref).split(/[\\/]/).pop();
    if (!name) throw new Error("缺少可恢复的 GeoJSON 引用");
    return "/artifacts/geojson/" + encodeURIComponent(name);
  }

  function renderRasterBounds(target, result, escapeHtml) {
    const bounds = result?.bounds;
    if (!Array.isArray(bounds) || bounds.length !== 4) {
      target.innerHTML = '<div class="map-empty">当前结果没有可预览的空间范围。</div>';
      return;
    }
    const width = bounds[2] - bounds[0], height = bounds[3] - bounds[1];
    const x = width >= height ? 12 : 12 + (1 - height / (width || 1)) * 238;
    const y = height >= width ? 12 : 12 + (1 - width / (height || 1)) * 118;
    const w = width >= height ? 476 : Math.max(8, 476 * width / (height || 1));
    const h = height >= width ? 236 : Math.max(8, 236 * height / (width || 1));
    target.innerHTML = '<svg viewBox="0 0 500 260" role="img" aria-label="栅格覆盖范围预览"><rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="6" fill="#b8d9cf" stroke="#087f8c" stroke-width="2"></rect><text x="250" y="244" text-anchor="middle" fill="#53656b" font-size="12">'
      + escapeHtml(result.dataset || "栅格") + " · " + escapeHtml(result.crs || "未知 CRS") + '</text></svg>';
  }

  function renderGeoJSON(target, geojson, helpers) {
    const all = (geojson?.features || []).filter(feature => feature?.geometry?.coordinates);
    if (!all.length) {
      target.innerHTML = '<div class="map-empty">当前结果没有可预览的几何形状。</div>';
      return;
    }
    const props = feature => feature.properties || {};
    const hasOverviewLayers = all.some(feature => ["roads", "water"].includes(props(feature).dataset));
    if (helpers.leaflet) {
      helpers.destroyMap();
      target.innerHTML = '<div id="leafletMap" aria-label="交互式空间预览"></div>';
      const map = helpers.leaflet.map("leafletMap", {zoomControl: true, attributionControl: false});
      helpers.setMap(map);
      if (hasOverviewLayers) renderOverviewLayers(map, all, helpers);
      else renderCandidateLayers(map, all, helpers);
      setTimeout(() => map.invalidateSize(), 0);
      return;
    }
    renderSvg(target, all, helpers);
  }

  function popup(feature, escapeHtml) {
    const props = feature.properties || {};
    return Object.keys(props).filter(key => key !== "geometry_source_crs").slice(0, 8).map(key => '<div><b>' + escapeHtml(key) + '</b>：' + escapeHtml(props[key]) + '</div>').join("") || "无属性信息";
  }

  function selectable(kind, feature, layer, helpers) {
    layer.on("click", () => helpers.selectFeature(feature));
    layer.bindPopup("<strong>" + kind + "</strong><br>" + popup(feature, helpers.escapeHtml));
  }

  function renderOverviewLayers(map, all, helpers) {
    const L = helpers.leaflet, props = feature => feature.properties || {};
    const groups = {
      boundary: all.filter(feature => props(feature).geometry_source === "geojson"),
      roads: all.filter(feature => props(feature).dataset === "roads"),
      water: all.filter(feature => props(feature).dataset === "water"),
    };
    const claimed = new Set([...groups.boundary, ...groups.roads, ...groups.water]);
    groups.other = all.filter(feature => !claimed.has(feature));
    const make = (items, style, kind) => L.geoJSON({type: "FeatureCollection", features: items}, {style, onEachFeature: (feature, layer) => selectable(kind, feature, layer, helpers)});
    const layers = {};
    if (groups.boundary.length) layers["行政区边界"] = make(groups.boundary, {color: "#087f8c", weight: 2.5, fillColor: "#87c7d1", fillOpacity: .28}, "行政区边界");
    if (groups.roads.length) layers["道路"] = make(groups.roads, {color: "#d97706", weight: 1.2, opacity: .85}, "道路");
    if (groups.water.length) layers["水体"] = make(groups.water, {color: "#2563eb", weight: 1.5, fillColor: "#60a5fa", fillOpacity: .35}, "水体");
    if (groups.other.length) layers["空间要素"] = make(groups.other, {color: "#64748b", weight: 1, fillOpacity: .35}, "空间要素");
    L.control.layers({}, layers, {collapsed: false, position: "topright"}).addTo(map);
    Object.values(layers).forEach(layer => layer.addTo(map));
    fitLayers(map, layers, L);
  }

  function renderCandidateLayers(map, all, helpers) {
    const L = helpers.leaflet, props = feature => feature.properties || {};
    const boundary = all.filter(feature => props(feature).geometry_source === "geojson");
    const candidates = all.filter(feature => props(feature).geometry_source === "raster-buildability-screening");
    const remainder = all.filter(feature => !boundary.includes(feature));
    const make = (items, style, kind) => L.geoJSON({type: "FeatureCollection", features: items}, {style, onEachFeature: (feature, layer) => selectable(kind, feature, layer, helpers)});
    const layers = {};
    if (boundary.length) layers["行政区边界"] = make(boundary, {color: "#087f8c", weight: 2.5, fillColor: "#87c7d1", fillOpacity: .28}, "行政区边界");
    layers[candidates.length ? "建设候选区域" : "空间要素"] = make(candidates.length ? candidates : remainder, {color: "#a6622b", weight: 1, fillColor: "#e09a5b", fillOpacity: .78}, "空间候选要素");
    const vectorOnly = L.layerGroup();
    const openStreetMap = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 19, attribution: "&copy; OpenStreetMap"});
    L.control.layers({"纯矢量": vectorOnly, "OpenStreetMap": openStreetMap}, layers, {collapsed: false, position: "topright"}).addTo(map);
    vectorOnly.addTo(map);
    Object.values(layers).forEach(layer => layer.addTo(map));
    fitLayers(map, layers, L);
  }

  function fitLayers(map, layers, L) {
    const values = Object.values(layers).filter(Boolean);
    if (!values.length) return;
    const bounds = L.featureGroup(values).getBounds();
    if (bounds.isValid()) map.fitBounds(bounds.pad(.08));
  }

  function renderSvg(target, all, helpers) {
    const escapeHtml = helpers.escapeHtml;
    const candidates = all.filter(feature => (feature.properties || {}).geometry_source === "raster-buildability-screening");
    const selected = candidates.length ? candidates : all;
    const coords = [];
    const walk = value => {
      if (!Array.isArray(value) || !value.length) return;
      if (typeof value[0] === "number" && Number.isFinite(value[0]) && Number.isFinite(value[1])) coords.push(value);
      else value.forEach(walk);
    };
    selected.forEach(feature => walk(feature.geometry.coordinates));
    if (!coords.length) {
      target.innerHTML = '<div class="map-empty">空间几何坐标无效，暂时无法预览。</div>';
      return;
    }
    const xs = coords.map(item => item[0]), ys = coords.map(item => item[1]);
    const minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
    const sx = x => 12 + (x - minx) / (maxx - minx || 1) * 476;
    const sy = y => 248 - (y - miny) / (maxy - miny || 1) * 236;
    const path = feature => {
      let output = "";
      const ring = values => {
        const points = (values || []).filter(point => Array.isArray(point) && Number.isFinite(point[0]) && Number.isFinite(point[1]));
        if (!points.length) return;
        output += "M " + sx(points[0][0]) + " " + sy(points[0][1]) + " ";
        points.slice(1).forEach(point => { output += "L " + sx(point[0]) + " " + sy(point[1]) + " "; });
        output += "Z ";
      };
      if (feature.geometry.type === "Polygon") feature.geometry.coordinates.forEach(ring);
      if (feature.geometry.type === "MultiPolygon") feature.geometry.coordinates.forEach(polygon => polygon.forEach(ring));
      return output;
    };
    const paths = selected.map((feature, index) => '<path data-feature-index="' + index + '" tabindex="0" d="' + path(feature) + '" fill="#e09a5b" stroke="#a6622b" stroke-width="1.1" opacity=".78"></path>').join("");
    target.innerHTML = '<svg viewBox="0 0 500 260" role="img" aria-label="GeoJSON 空间预览"><rect width="500" height="260" fill="#edf3f1"></rect>' + paths
      + '<text x="12" y="22" fill="#176a49" font-size="12">' + escapeHtml(candidates.length ? "建设候选区域" : "空间要素") + " · " + selected.length + ' 个面</text></svg>';
    if (typeof target.querySelectorAll !== "function") return;
    target.querySelectorAll("path[data-feature-index]").forEach(element => {
      const choose = () => {
        const feature = selected[Number(element.dataset.featureIndex)];
        if (feature) helpers.selectFeature(feature);
      };
      element.addEventListener("click", choose);
      element.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          choose();
        }
      });
    });
  }

  return Object.freeze({SCHEMA_VERSION, createMapAdapter});
});
