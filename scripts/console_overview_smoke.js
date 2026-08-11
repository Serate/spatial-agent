/*
 * Repeatable browser contract smoke for the spatial overview result and layers.
 * Start scripts/console_cdp_start.ps1 first, then run with Node.js.
 */

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const cdpBase = process.env.CDP_URL || "http://127.0.0.1:9222";
const consoleUrl = process.env.CONSOLE_URL || "http://127.0.0.1:8088/";
const backend = process.env.CONSOLE_BACKEND || "memory";
const request = process.env.OVERVIEW_REQUEST || "分析洪山区空间概况";

let pages;
try {
  const response = await fetch(`${cdpBase}/json/list`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  pages = await response.json();
} catch (error) {
  throw new Error(`无法连接 Chrome CDP（${cdpBase}）。先运行 scripts/console_cdp_start.ps1。${error.message}`);
}
const page = pages.find(item => item.type === "page");
if (!page) throw new Error("Chrome CDP 没有可用页面");

const socket = new WebSocket(page.webSocketDebuggerUrl);
let nextId = 0;
const pending = new Map();
socket.onmessage = event => {
  const message = JSON.parse(event.data);
  const resolve = pending.get(message.id);
  if (resolve) {
    pending.delete(message.id);
    resolve(message);
  }
};
const command = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++nextId;
  pending.set(id, resolve);
  socket.send(JSON.stringify({id, method, params}));
  setTimeout(() => {
    if (pending.delete(id)) reject(new Error(`CDP timeout: ${method}`));
  }, 90000);
});
await new Promise((resolve, reject) => {
  socket.onopen = resolve;
  socket.onerror = () => reject(new Error("Chrome CDP WebSocket 连接失败"));
});
await command("Page.enable");
await command("Runtime.enable");
await command("Page.navigate", {url: consoleUrl});
for (let attempt = 0; attempt < 60; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "typeof $ === 'function' && typeof sendChat === 'function'",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 59) throw new Error("Console 页面脚本未就绪");
}

const evaluate = async (expression) => {
  const result = await command("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.result?.exceptionDetails) {
    throw new Error(result.result.exceptionDetails.exception?.description || "浏览器脚本执行失败");
  }
  return result.result?.result?.value;
};

const runSnapshot = await evaluate(`(async()=>{
  $('backend').value=${JSON.stringify(backend)};
  await newSession();
  await sendChat(${JSON.stringify(request)});
  for(let i=0;i<120;i++){
    await new Promise(resolve=>setTimeout(resolve,250));
    const panel=document.querySelector('.overview-result');
    if(panel?.classList.contains('is-visible') || $('status')?.textContent==='失败') break;
  }
  return JSON.stringify({
    status:$('status')?.textContent||'',
    decision:$('decisionMode')?.textContent||'',
    panel:Boolean(document.querySelector('.overview-result.is-visible')),
    stats:$('overviewStats')?.textContent||'',
    evidence:$('overviewEvidence')?.textContent||'',
    error:$('error')?.textContent||''
  });
})()`);
const run = JSON.parse(runSnapshot || "{}");
if (!run.panel) {
  throw new Error(`空间总览面板未显示：${JSON.stringify(run)}`);
}
if (!run.stats.includes("工具步骤") || !run.stats.includes("数据来源") || !run.stats.includes("空间要素")) {
  throw new Error(`空间总览摘要缺少公共指标：${JSON.stringify(run)}`);
}

// 用固定的最小结果验证前端分层，不依赖 Docker 是否挂载可选道路/水体文件。
const layersSnapshot = await evaluate(`(()=>{
  const polygon=(x,y)=>({type:'Feature',properties:{...x},geometry:{type:'Polygon',coordinates:[[[y,y],[y+0.02,y],[y+0.02,y+0.02],[y,y+0.02],[y,y]]]}});
  const fixture={result_type:'spatial_overview_result',features:[
    polygon({geometry_source:'geojson',name:'洪山区'},114.30),
    {type:'Feature',properties:{dataset:'roads',name:'道路示例'},geometry:{type:'LineString',coordinates:[[114.31,30.48],[114.33,30.50]]}},
    polygon({dataset:'water',name:'水体示例'},114.34)
  ]};
  const rendered=spatialOverviewMapPreview(fixture);
  const labels=[...document.querySelectorAll('#leafletMap .leaflet-control-layers-overlays label')].map(x=>x.textContent.trim());
  const paths=[...document.querySelectorAll('#leafletMap .leaflet-overlay-pane path')];
  const colors=paths.map(x=>x.getAttribute('stroke')||x.style.stroke||'');
  return JSON.stringify({rendered,labels,colors,pathCount:paths.length,map:Boolean(document.querySelector('#leafletMap'))});
})()`);
const layers = JSON.parse(layersSnapshot || "{}");
console.log(JSON.stringify({run, layers}));
if (!layers.rendered || !layers.map || layers.pathCount < 3) {
  throw new Error(`空间总览地图没有渲染足够要素：${JSON.stringify(layers)}`);
}
for (const label of ["行政区边界", "道路", "水体"]) {
  if (!layers.labels.some(value => value.includes(label))) {
    throw new Error(`地图缺少${label}图层：${JSON.stringify(layers.labels)}`);
  }
}
for (const color of ["#087f8c", "#d97706", "#2563eb"]) {
  if (!layers.colors.some(value => value.toLowerCase() === color)) {
    throw new Error(`地图缺少颜色 ${color}：${JSON.stringify(layers.colors)}`);
  }
}

const releaseSnapshot = await evaluate(`(()=>{
  const fixture={analysis_ready:{status:'ready',derived_version:'analysis-ready-v1',verification_mode:'metadata',grid_alignment:{status:'aligned'},source_binding:{status:'recorded',fingerprint:'sha256:test-source'},output_manifest:{status:'ready',verification_mode:'metadata',hashes_verified:false,mismatch_count:0,outputs:{dem:{reported:'dem_aligned.tif',manifest:['dem_aligned.tif'],matched:true},land_use:{reported:'land_use_aligned.tif',manifest:['land_use_aligned.tif'],matched:true}}}},result:{geometry:{status:'boundary_geometry',available:true,feature_count:1,sources:['geojson'],crs:['EPSG:4326']}}};
  renderEvidence(fixture);
  return JSON.stringify({text:document.querySelector('#releaseEvidence')?.textContent||'',className:document.querySelector('#releaseEvidence')?.className||''});
})()`);
const release = JSON.parse(releaseSnapshot || "{}");
if (!release.text.includes("发布完整性") || !release.text.includes("源绑定 SHA-256") || !release.text.includes("输出 manifest") || !release.text.includes("dem_aligned.tif")) {
  throw new Error(`发布完整性证据卡缺少三层摘要：${JSON.stringify(release)}`);
}
socket.close();
