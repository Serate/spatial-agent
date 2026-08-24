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
    const summaryTarget = () => typeof options.summaryTarget === "function" ? options.summaryTarget() : options.summaryTarget;
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
      const summary = summaryTarget();
      const button = useSelectionButton();
      if (label) label.textContent = "点击可视化要素后，可将其作为下一次请求的领域上下文。";
      if (summary) summary.textContent = "交互式地图";
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
      const summary = summaryTarget();
      const button = useSelectionButton();
      if (label) label.textContent = adminName ? "已选中：" + adminName + " · " + (selected.crs || "未知 CRS") : "已选中空间要素，但缺少可绑定的区域名称。";
      if (summary && adminName) summary.textContent = "已选中 · " + adminName;
      if (button) button.disabled = !adminName;
      if (typeof options.onSelection === "function") options.onSelection(Object.assign({}, selected));
    }

    async function render(contextValue) {
      const view = contextValue.view || {};
      const target = contextValue.target;
      if (!target) return {visible: false};
      if (view.mode === "raster_bounds") {
        destroyMap();
        renderRasterBounds(target, view, {
          leaflet: leaflet(),
          escapeHtml,
          setMap: value => { map = value; },
        });
        const summary = summaryTarget();
        if (summary) summary.textContent = "栅格范围 · " + (view.dataset || "当前数据");
        return {visible: true};
      }
      if (view.mode !== "geojson") {
        target.innerHTML = '<div class="map-empty">当前 renderer 没有收到可绘制几何。</div>';
        return {visible: true};
      }
      try {
        const geojson = view.geojson || await fetchJson(artifactPath(contextValue.run, view));
        if (!contextValue.isCurrent()) return {visible: false};
        const summary = summaryTarget();
        const count = Array.isArray(geojson?.features) ? geojson.features.length : 0;
        if (summary) summary.textContent = "空间图层 · " + count + " 个要素";
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

  function renderRasterBounds(target, result, helpers) {
    const values = Array.isArray(result?.bounds) && result.bounds.length === 4
      ? result.bounds.map(value => Number(value))
      : [];
    if (values.length !== 4 || values.some(value => !Number.isFinite(value))) {
      target.innerHTML = '<div class="map-empty">当前结果没有可预览的空间范围。</div>';
      return;
    }
    const mapBounds = toLeafletBounds(values, result.crs);
    if (helpers.leaflet && mapBounds) {
      try {
        target.innerHTML = '<div data-raster-map class="raster-map-leaflet" role="img" aria-label="按真实坐标定位的栅格外接范围"></div>';
        const element = target.querySelector?.("[data-raster-map]");
        if (!element) throw new Error("地图容器不可用");
        const L = helpers.leaflet;
        const map = L.map(element, {zoomControl: true, attributionControl: true});
        helpers.setMap(map);
        const leafletBounds = [[mapBounds[1], mapBounds[0]], [mapBounds[3], mapBounds[2]]];
        const rectangle = L.rectangle(leafletBounds, {
          color: "#7c3aed",
          weight: 2,
          dashArray: "8 6",
          fill: false,
          fillOpacity: 0,
        }).addTo(map);
        const layers = {"栅格外接范围": rectangle};
        addBaseLayers(map, layers, L);
        map.fitBounds(leafletBounds, {padding: [24, 24]});
        mapToolbar(map, layers, L, target);
        appendHtml(target, '<div class="map-overlay-note"><strong>仅显示栅格外接范围</strong> · 已按真实坐标定位 · 不代表有效像元覆盖</div>');
        setTimeout(() => map.invalidateSize?.(), 0);
        return;
      } catch (error) {
        helpers.setMap?.(null);
      }
    }
    renderRasterBoundsSvg(target, {bounds: values, dataset: result.dataset, crs: result.crs}, helpers.escapeHtml);
  }

  function toLeafletBounds(bounds, crs) {
    const code = String(crs || "").toUpperCase().replace(/\s+/g, "");
    if (["EPSG:4326", "EPSG:4258", "EPSG:4490", "CRS:84", "WGS84"].includes(code)) return normalizedBounds(bounds);
    if (["EPSG:3857", "EPSG:900913", "EPSG:3785"].includes(code)) {
      const lower = webMercatorToLonLat(bounds[0], bounds[1]);
      const upper = webMercatorToLonLat(bounds[2], bounds[3]);
      return normalizedBounds([lower[0], lower[1], upper[0], upper[1]]);
    }
    return null;
  }

  function normalizedBounds(bounds) {
    return [Math.min(bounds[0], bounds[2]), Math.min(bounds[1], bounds[3]), Math.max(bounds[0], bounds[2]), Math.max(bounds[1], bounds[3])];
  }

  function webMercatorToLonLat(x, y) {
    const longitude = x / 20037508.34 * 180;
    const latitudeDegrees = y / 20037508.34 * 180;
    const latitude = 180 / Math.PI * (2 * Math.atan(Math.exp(latitudeDegrees * Math.PI / 180)) - Math.PI / 2);
    return [longitude, latitude];
  }

  function renderRasterBoundsSvg(target, result, escapeHtml) {
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
    target.innerHTML = '<div class="raster-map-fallback"><svg viewBox="0 0 500 260" role="img" aria-label="栅格外接范围预览（非有效像元边界）"><defs><pattern id="rasterGrid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M 24 0 L 0 0 0 24" fill="none" stroke="#c4b5fd" stroke-width=".7" opacity=".55"></path></pattern></defs><rect width="500" height="260" fill="#f5f3ff"></rect><rect width="500" height="260" fill="url(#rasterGrid)"></rect><line x1="250" y1="26" x2="250" y2="238" stroke="#a78bfa" stroke-dasharray="3 5" opacity=".45"></line><line x1="18" y1="132" x2="482" y2="132" stroke="#a78bfa" stroke-dasharray="3 5" opacity=".45"></line><rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="2" fill="none" stroke="#7c3aed" stroke-width="2.4" stroke-dasharray="8 6"></rect><text x="18" y="24" fill="#5b21b6" font-size="12" font-weight="700">栅格外接范围（仅范围证据）</text><text x="250" y="247" text-anchor="middle" fill="#475569" font-size="12">'
      + escapeHtml(result.dataset || "栅格") + " · " + escapeHtml(result.crs || "未知 CRS") + '</text></svg></div>';
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
      const map = helpers.leaflet.map("leafletMap", {zoomControl: true, attributionControl: true});
      helpers.setMap(map);
      const layers = hasOverviewLayers ? renderOverviewLayers(map, all, helpers) : renderCandidateLayers(map, all, helpers);
      appendHtml(target, mapLegendEntries(all, escapeHtml));
      appendHtml(target, mapOverlay(all, escapeHtml));
      mapToolbar(map, layers, helpers.leaflet, target);
      setTimeout(() => map.invalidateSize(), 0);
      return;
    }
    renderSvg(target, all, helpers);
  }

  function popup(feature, escapeHtml) {
    const props = feature.properties || {};
    const labels = {name: "名称", admin_name: "行政区", area_name: "区域", dataset: "数据集", geometry_source: "几何来源", geometry_crs: "坐标系", class: "类别", land_use: "土地利用", slope_max: "最大坡度", distance_to_road: "距道路"};
    const value = item => typeof item === "object" ? JSON.stringify(item) : item;
    return Object.keys(props).filter(key => key !== "geometry_source_crs" && !key.startsWith("_")).slice(0, 8).map(key => '<div><b>' + escapeHtml(labels[key] || key) + '</b>：' + escapeHtml(value(props[key])) + '</div>').join("") || "无属性信息";
  }

  function featureLabel(kind, feature) {
    const props = feature?.properties || {};
    return props.name || props.admin_name || props.area_name || ({roads: "道路", water: "水体"}[props.dataset] || kind || "空间要素");
  }

  function selectable(kind, feature, layer, helpers, style = {}) {
    const label = featureLabel(kind, feature);
    if (typeof layer.on === "function") {
      layer.on("click", () => helpers.selectFeature(feature));
      layer.on("mouseover", () => layer.setStyle?.({weight: (style.weight || 1) + 1, fillOpacity: Math.min(.78, (style.fillOpacity || .08) + .16), opacity: 1}));
      layer.on("mouseout", () => layer.setStyle?.(style));
    }
    if (typeof layer.bindTooltip === "function") layer.bindTooltip(label, {sticky: true, direction: "top", opacity: .92});
    if (typeof layer.bindPopup === "function") layer.bindPopup("<strong>" + helpers.escapeHtml(label) + "</strong><br>" + popup(feature, helpers.escapeHtml));
  }

  function mapLegendEntries(features, escapeHtml) {
    const props = feature => feature.properties || {};
    const entries = [];
    if (features.some(feature => props(feature).geometry_source === "geojson")) entries.push({className: "boundary", label: "行政区边界"});
    if (features.some(feature => props(feature).geometry_source === "raster-buildability-screening")) entries.push({className: "candidate", label: "建设候选区域"});
    if (features.some(feature => props(feature).dataset === "roads")) entries.push({className: "road", label: "道路"});
    if (features.some(feature => props(feature).dataset === "water")) entries.push({className: "water", label: "水体"});
    if (!entries.length && features.length) entries.push({className: "feature", label: "空间要素"});
    return '<div class="map-legend" role="group" aria-label="地图图例">' + entries.map(item => '<span><i class="map-swatch ' + item.className + '" aria-hidden="true"></i>' + escapeHtml(item.label) + '</span>').join("") + '</div>';
  }

  function appendHtml(target, html) {
    if (typeof target.insertAdjacentHTML === "function") target.insertAdjacentHTML("beforeend", html);
    else target.innerHTML += html;
  }

  function mapOverlay(features, escapeHtml) {
    return '<div class="map-overlay-note"><strong>空间预览</strong> · ' + escapeHtml(features.length) + ' 个要素 · 悬停查看名称</div>';
  }

  function mapToolbar(map, layers, L, target) {
    if (L.control && typeof L.control.scale === "function") L.control.scale({imperial: false, position: "bottomright"}).addTo(map);
    appendHtml(target, '<div class="map-command"><button type="button" data-map-fit aria-label="适合所有空间要素">适合视图</button></div>');
    const button = target.querySelector?.("[data-map-fit]");
    if (button) button.addEventListener("click", () => fitLayers(map, layers, L));
  }

  function addBaseLayers(map, layers, L) {
    const vectorOnly = L.layerGroup();
    const openStreetMap = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 19, attribution: "&copy; OpenStreetMap"});
    let tileErrors = 0;
    if (typeof openStreetMap.on === "function") openStreetMap.on("tileerror", () => {
      tileErrors += 1;
      if (tileErrors >= 3 && map.hasLayer?.(openStreetMap)) {
        map.removeLayer(openStreetMap);
        vectorOnly.addTo(map);
      }
    });
    if (L.control && typeof L.control.layers === "function") L.control.layers({"OpenStreetMap": openStreetMap, "纯矢量": vectorOnly}, layers, {collapsed: false, position: "topright"}).addTo(map);
    openStreetMap.addTo(map);
    return vectorOnly;
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
    const make = (items, style, kind) => L.geoJSON({type: "FeatureCollection", features: items}, {style, onEachFeature: (feature, layer) => selectable(kind, feature, layer, helpers, style)});
    const layers = {};
    if (groups.boundary.length) layers["行政区边界"] = make(groups.boundary, {color: "#087f8c", weight: 2.5, fillColor: "#87c7d1", fillOpacity: .28}, "行政区边界");
    if (groups.roads.length) layers["道路"] = make(groups.roads, {color: "#d97706", weight: 1.2, opacity: .85}, "道路");
    if (groups.water.length) layers["水体"] = make(groups.water, {color: "#2563eb", weight: 1.5, fillColor: "#60a5fa", fillOpacity: .35}, "水体");
    if (groups.other.length) layers["空间要素"] = make(groups.other, {color: "#64748b", weight: 1, fillOpacity: .35}, "空间要素");
    addBaseLayers(map, layers, L);
    Object.values(layers).forEach(layer => layer.addTo(map));
    fitLayers(map, layers, L);
    return layers;
  }

  function renderCandidateLayers(map, all, helpers) {
    const L = helpers.leaflet, props = feature => feature.properties || {};
    const boundary = all.filter(feature => props(feature).geometry_source === "geojson");
    const candidates = all.filter(feature => props(feature).geometry_source === "raster-buildability-screening");
    const remainder = all.filter(feature => !boundary.includes(feature));
    const make = (items, style, kind) => L.geoJSON({type: "FeatureCollection", features: items}, {style, onEachFeature: (feature, layer) => selectable(kind, feature, layer, helpers, style)});
    const layers = {};
    if (boundary.length) layers["行政区边界"] = make(boundary, {color: "#087f8c", weight: 2.5, fillColor: "#87c7d1", fillOpacity: .28}, "行政区边界");
    layers[candidates.length ? "建设候选区域" : "空间要素"] = make(candidates.length ? candidates : remainder, {color: "#a6622b", weight: 1, fillColor: "#e09a5b", fillOpacity: .78}, "空间候选要素");
    addBaseLayers(map, layers, L);
    Object.values(layers).forEach(layer => layer.addTo(map));
    fitLayers(map, layers, L);
    return layers;
  }

  function fitLayers(map, layers, L) {
    const values = Object.values(layers).filter(Boolean);
    if (!values.length) return;
    const bounds = L.featureGroup(values).getBounds();
    if (bounds.isValid()) map.fitBounds(bounds.pad(.08));
  }

  function renderSvg(target, all, helpers) {
    const escapeHtml = helpers.escapeHtml;
    const selected = all;
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
      const line = values => {
        const points = (values || []).filter(point => Array.isArray(point) && Number.isFinite(point[0]) && Number.isFinite(point[1]));
        if (!points.length) return;
        output += "M " + sx(points[0][0]) + " " + sy(points[0][1]) + " ";
        points.slice(1).forEach(point => { output += "L " + sx(point[0]) + " " + sy(point[1]) + " "; });
      };
      const ring = values => {
        const points = (values || []).filter(point => Array.isArray(point) && Number.isFinite(point[0]) && Number.isFinite(point[1]));
        if (!points.length) return;
        output += "M " + sx(points[0][0]) + " " + sy(points[0][1]) + " ";
        points.slice(1).forEach(point => { output += "L " + sx(point[0]) + " " + sy(point[1]) + " "; });
        output += "Z ";
      };
      if (feature.geometry.type === "LineString") line(feature.geometry.coordinates);
      if (feature.geometry.type === "MultiLineString") feature.geometry.coordinates.forEach(line);
      if (feature.geometry.type === "Polygon") feature.geometry.coordinates.forEach(ring);
      if (feature.geometry.type === "MultiPolygon") feature.geometry.coordinates.forEach(polygon => polygon.forEach(ring));
      return output;
    };
    const styles = feature => {
      const props = feature.properties || {};
      if (props.dataset === "roads") return {fill: "none", stroke: "#d97706", opacity: ".9", width: "1.4"};
      if (props.dataset === "water") return {fill: "#60a5fa", stroke: "#2563eb", opacity: ".42", width: "1.2"};
      if (props.geometry_source === "geojson") return {fill: "#87c7d1", stroke: "#087f8c", opacity: ".32", width: "2.2"};
      if (props.geometry_source === "raster-buildability-screening") return {fill: "#e09a5b", stroke: "#a6622b", opacity: ".78", width: "1.1"};
      return {fill: "#94a3b8", stroke: "#64748b", opacity: ".38", width: "1"};
    };
    const paths = selected.map((feature, index) => { const style = styles(feature); return '<path data-feature-index="' + index + '" tabindex="0" d="' + path(feature) + '" fill="' + style.fill + '" stroke="' + style.stroke + '" stroke-width="' + style.width + '" opacity="' + style.opacity + '"></path>'; }).join("");
    target.innerHTML = '<svg viewBox="0 0 500 260" role="img" aria-label="GeoJSON 空间预览"><rect width="500" height="260" fill="#edf3f1"></rect>' + paths
      + '<text x="12" y="22" fill="#176a49" font-size="12">空间要素 · ' + selected.length + ' 个</text></svg>';
    appendHtml(target, mapOverlay(selected, escapeHtml));
    appendHtml(target, mapLegendEntries(selected, escapeHtml));
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
