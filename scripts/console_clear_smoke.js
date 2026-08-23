const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const consoleUrl = process.env.CONSOLE_URL || "http://127.0.0.1:8088/";
const cdpUrl = process.env.CDP_URL || "http://127.0.0.1:9222";
const pages = await (await fetch(`${cdpUrl}/json/list`)).json();
const page = pages.find(item => item.type === "page");
if (!page) throw new Error("Chrome CDP page was not found");

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
  }, 15000);
});
await new Promise(resolve => { socket.onopen = resolve; });
await command("Page.enable");
await command("Runtime.enable");
await command("Page.navigate", {url: consoleUrl});
for (let attempt = 0; attempt < 60; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "typeof $ === 'function' && typeof sendChat === 'function' && Boolean(window.__consoleBootstrapReady && window.__consoleDomainReady)",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 59) throw new Error("Console 页面脚本未就绪");
}
const result = await command("Runtime.evaluate", {
  expression: "(async()=>{ $('answer').textContent='旧分析结论'; $('steps').textContent='旧执行步骤'; const feature={type:'Feature',properties:{name:'洪山区',geometry_source:'fixture'},geometry:{type:'Polygon',coordinates:[[[114.30,30.48],[114.32,30.48],[114.32,30.50],[114.30,30.50],[114.30,30.48]]]}}; const report=await rendererRegistry.renderWorkspace({panels:{map:{kind:'map',mode:'geojson',geojson:{type:'FeatureCollection',features:[feature]}}},specs:[{id:'map',renderer:'map'}],surfaces:{generic:$('genericResult'),visual:$('map')}}); const path=document.querySelector('#leafletMap .leaflet-overlay-pane path')||document.querySelector('#map svg path'); if(!path) throw new Error('地图 fixture 未渲染：'+JSON.stringify(report)+' · '+$('map').textContent); path.dispatchEvent(new MouseEvent('click',{bubbles:true})); await new Promise(resolve=>setTimeout(resolve,50)); const before=rendererRegistry.context(),selectionBefore=$('mapSelection').textContent,pathIndex=path.dataset.featureIndex; await clearChat(); return JSON.stringify({before,after:rendererRegistry.context(),answer:$('answer').textContent,steps:$('steps').textContent,selectionBefore,pathIndex,selection:$('mapSelection').textContent,selectionEnabled:!$('useMapSelection').disabled})})()",
  awaitPromise: true,
  returnByValue: true,
});
if (result.result.exceptionDetails) {
  throw new Error(result.result.exceptionDetails.exception?.description || "clear action failed");
}
const snapshot = JSON.parse(result.result.result.value);
console.log(JSON.stringify(snapshot));
if (!snapshot.before?.spatial_context?.admin_name || Object.keys(snapshot.after || {}).length || snapshot.answer || snapshot.steps || !snapshot.selection.includes("下一次请求的领域上下文") || snapshot.selectionEnabled) {
  throw new Error("清空对话没有清除当前工作区");
}
socket.close();
process.exit(0);
