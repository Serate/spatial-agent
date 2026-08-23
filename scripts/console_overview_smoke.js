/*
 * Repeatable browser contract smoke for the spatial overview result and layers.
 * Start scripts/console_cdp_start.ps1 first, then run with Node.js.
 */

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const cdpBase = process.env.CDP_URL || "http://127.0.0.1:9222";
const consoleUrl = process.env.CONSOLE_URL || "http://127.0.0.1:8088/";
const backend = process.env.CONSOLE_BACKEND || "memory";
const planner = process.env.CONSOLE_PLANNER || "rule";
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
await command("Network.enable");
await command("Network.setCacheDisabled", {cacheDisabled: true});
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
  $('planner').value=${JSON.stringify(planner)};
  $('backend').value=${JSON.stringify(backend)};
  await newSession();
  await sendChat(${JSON.stringify(request)});
  for(let i=0;i<120;i++){
    await new Promise(resolve=>setTimeout(resolve,250));
    const panel=document.querySelector('.generic-result');
    if((panel?.classList.contains('is-visible') && $('lineageEvidence')?.textContent.includes('运行 ID')) || $('status')?.textContent==='失败') break;
  }
  return JSON.stringify({
    status:$('status')?.textContent||'',
    decision:$('decisionMode')?.textContent||'',
    panel:Boolean(document.querySelector('.generic-result.is-visible')),
    stats:$('genericResult')?.textContent||'',
    selectionEvidence:$('selectionEvidence')?.textContent||'',
    lineage:$('lineageEvidence')?.textContent||'',
    error:$('error')?.textContent||''
  });
})()`);
const run = JSON.parse(runSnapshot || "{}");
if (!run.panel) {
  throw new Error(`统一动态结果视图未显示空间总览：${JSON.stringify(run)}`);
}
if (!run.lineage.includes('运行 ID')) {
  throw new Error('结果证据索引未显示运行 ID: ' + run.lineage);
}
if (!run.selectionEvidence.includes('Evidence Registry') || !run.selectionEvidence.includes('工作流选择') || !run.selectionEvidence.includes('规划器选择')) {
  throw new Error('选择证据没有通过通用 Evidence Registry renderer 展示: ' + run.selectionEvidence);
}
if (!run.stats.includes("工具步骤") || !run.stats.includes("数据来源") || !run.stats.includes("空间要素")) {
  throw new Error(`空间总览摘要缺少公共指标：${JSON.stringify(run)}`);
}

// 用固定的最小 workspace 验证 Registry 的视觉与通用 surface，不依赖可选数据文件。
const layersSnapshot = await evaluate(`(async()=>{
  const polygon=(x,y)=>({type:'Feature',properties:{...x},geometry:{type:'Polygon',coordinates:[[[y,y],[y+0.02,y],[y+0.02,y+0.02],[y,y+0.02],[y,y]]]}});
  const geojson={type:'FeatureCollection',features:[
    polygon({geometry_source:'geojson',name:'洪山区'},114.30),
    {type:'Feature',properties:{dataset:'roads',name:'道路示例'},geometry:{type:'LineString',coordinates:[[114.31,30.48],[114.33,30.50]]}},
    polygon({dataset:'water',name:'水体示例'},114.34)
  ]};
  const report=await rendererRegistry.renderWorkspace({
    panels:{
      overview_map:{kind:'map',title:'空间概览地图',mode:'geojson',geojson},
      overview_metrics:{kind:'metrics',title:'概览统计',metrics:[
        {label:'空间要素',value:3},
        {label:'数据来源',value:'内联契约 fixture'}
      ]}
    },
    specs:[
      {id:'overview_map',renderer:'map',title:'空间概览地图'},
      {id:'overview_metrics',renderer:'metrics',title:'概览统计'}
    ],
    run:{run_id:'renderer-registry-smoke'},
    surfaces:{generic:$('genericResult'),visual:$('map')},
    onSurface:(surface,visible)=>{
      if(surface==='generic') setResultPanel('.generic-result',visible);
      if(surface==='visual') setResultPanel('.map-result',visible);
    }
  });
  await new Promise(resolve=>setTimeout(resolve,50));
  const labels=[...document.querySelectorAll('#leafletMap .leaflet-control-layers-overlays label')].map(x=>x.textContent.trim());
  const paths=[...document.querySelectorAll('#leafletMap .leaflet-overlay-pane path')];
  const colors=paths.map(x=>x.getAttribute('stroke')||x.style.stroke||'');
  return JSON.stringify({
    report,
    labels,
    colors,
    pathCount:paths.length,
    map:Boolean(document.querySelector('#leafletMap')),
    visualSurface:Boolean(document.querySelector('.map-result.is-visible')),
    genericSurface:Boolean(document.querySelector('.generic-result.is-visible')),
    genericText:$('genericResult')?.textContent||''
  });
})()`);
const layers = JSON.parse(layersSnapshot || "{}");
console.log(JSON.stringify({run, layers}));
if (layers.report?.status !== "rendered" || !layers.report?.rendered_surfaces?.includes("visual") || !layers.report?.rendered_surfaces?.includes("generic")) {
  throw new Error(`Renderer Registry 没有完成两个 surface：${JSON.stringify(layers)}`);
}
if (!layers.visualSurface || !layers.map || layers.pathCount < 3) {
  throw new Error(`空间总览地图没有渲染足够要素：${JSON.stringify(layers)}`);
}
if (!layers.genericSurface || !layers.genericText.includes("概览统计") || !layers.genericText.includes("空间要素") || !layers.genericText.includes("内联契约 fixture")) {
  throw new Error(`通用结构化结果没有通过 Registry 渲染：${JSON.stringify(layers)}`);
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

const actionSnapshot = await evaluate(`(()=>{
  const target=document.createElement('div'); document.body.appendChild(target);
  const mounted=window.ConsoleActionHost.mount({target,catalog:{domain_id:'text',actions:[
    {id:'text.normalize',label:'文本规范化',input_schema:{type:'object',required:['text'],properties:{text:{type:'string',title:'文本',default:'示例'}}}},
    {id:'text.stats',label:'文本统计',input_schema:{type:'object',required:['limit'],properties:{limit:{type:'integer',title:'限制',default:10,minimum:1,maximum:20}}}}
  ]}});
  const select=target.querySelector('#domainActionSelect');
  const first={options:select.options.length,text:target.textContent,value:target.querySelector('[data-action-field]')?.value||''};
  select.value='text.stats'; select.dispatchEvent(new Event('change'));
  const second={text:target.textContent,type:target.querySelector('[data-action-field]')?.dataset.actionType||'',value:target.querySelector('[data-action-field]')?.value||''};
  const actualOptions=document.querySelector('#domainActionSelect')?.options.length||0;
  target.remove();
  return JSON.stringify({mounted,first,second,actualOptions});
})()`);
const action = JSON.parse(actionSnapshot || "{}");
if (action.mounted?.action_count !== 2 || action.first?.options !== 2 || action.first?.value !== "示例" || action.second?.type !== "integer" || action.second?.value !== "10" || action.actualOptions < 1) {
  throw new Error(`Action Host 未按 schema 动态生成表单：${JSON.stringify(action)}`);
}

const releaseSnapshot = await evaluate(`(()=>{
  const fixture={analysis_ready:{status:'ready',derived_version:'analysis-ready-v1',verification_mode:'metadata',grid_alignment:{status:'aligned'},source_binding:{status:'recorded',fingerprint:'sha256:test-source'},output_manifest:{status:'ready',verification_mode:'metadata',hashes_verified:false,mismatch_count:0,outputs:{dem:{reported:'dem_aligned.tif',manifest:['dem_aligned.tif'],matched:true},land_use:{reported:'land_use_aligned.tif',manifest:['land_use_aligned.tif'],matched:true}}}},result:{geometry:{status:'boundary_geometry',available:true,feature_count:1,sources:['geojson'],crs:['EPSG:4326']}}};
  renderEvidence(fixture);
  return JSON.stringify({text:document.querySelector('#releaseEvidence')?.textContent||'',className:document.querySelector('#releaseEvidence')?.className||'',link:document.querySelector('#releaseEvidence a')?.getAttribute('href')||''});
})()`);
const release = JSON.parse(releaseSnapshot || "{}");
if (!release.text.includes("发布完整性") || !release.text.includes("源绑定 SHA-256") || !release.text.includes("输出 manifest") || !release.text.includes("dem_aligned.tif") || !release.link.includes("/release-evidence")) {
  throw new Error(`发布完整性证据卡缺少三层摘要：${JSON.stringify(release)}`);
}
socket.close();
process.exit(0);
