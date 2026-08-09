/* Browser smoke check for the interactive console map. Requires Chrome started with CDP. */

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const consoleUrl = process.env.CONSOLE_URL || "http://127.0.0.1:8088/";
const mapRequest = process.env.MAP_REQUEST || "分析洪山区建设适宜性，坡度不超过20度";
const response = await fetch("http://127.0.0.1:9222/json/list");
const pages = await response.json();
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
await sleep(1500);
const sendResult = await command("Runtime.evaluate", {
  expression: "(async()=>{ $('backend').value='local'; const response=await nativeFetch('/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request:"+JSON.stringify(mapRequest)+",planner:'rule',backend:'local',session_id:'browser-map',export_artifact:true,export_geojson:true})}); const data=await response.json(); renderRun(data); })()",
  awaitPromise: true,
});
if (sendResult.result.exceptionDetails) {
  throw new Error(sendResult.result.exceptionDetails.exception?.description || "console request failed");
}
await sleep(1500);
for (let attempt = 0; attempt < 30; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "Boolean(window.leafletMap || document.querySelector('#map svg path'))",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
}
const clicked = await command("Runtime.evaluate", {
  expression: "(()=>{let done=false; leafletMap.eachLayer(layer=>{if(layer.eachLayer) layer.eachLayer(item=>{if(!done&&item.fire){item.fire('click'); done=true;}})}); return done;})()",
  returnByValue: true,
});
if (!clicked.result?.result?.value) {
  const debug = await command("Runtime.evaluate", {
    expression: "JSON.stringify({status:$('status')?.textContent,title:$('title')?.textContent,decision:$('decisionMode')?.textContent,map:$('map')?.innerHTML?.slice(0,500),geo:$('links')?.innerHTML||'',error:$('error')?.textContent||''})",
    returnByValue: true,
  });
  throw new Error("空间预览没有可点击的矢量要素: " + (debug.result?.result?.value || "unknown"));
}
const result = await command("Runtime.evaluate", {
  expression: `JSON.stringify({
    leaflet: Boolean(document.querySelector('#leafletMap')),
    leafletPaths: document.querySelectorAll('.leaflet-overlay-pane path').length,
    svgPaths: document.querySelectorAll('#map svg path').length,
    empty: Boolean(document.querySelector('#map .map-empty')),
    status: document.querySelector('#status')?.textContent,
    selection: document.querySelector('#mapSelection')?.textContent,
    selectionEnabled: !document.querySelector('#useMapSelection')?.disabled
  })`,
  returnByValue: true,
});
const snapshot = JSON.parse(result.result.result.value);
console.log(JSON.stringify(snapshot));
if (snapshot.leafletPaths < 1 && snapshot.svgPaths < 1) {
  throw new Error("空间预览没有生成任何矢量图层");
}
if (!snapshot.selection.includes("洪山区") || !snapshot.selectionEnabled) {
  throw new Error("地图要素点击没有生成可用的空间上下文");
}

const cleared = await command("Runtime.evaluate", {
  expression: "(()=>{ $('clearChat').click(); return JSON.stringify({selection: $('mapSelection')?.textContent, selectionEnabled: !$('useMapSelection')?.disabled, answer: $('answer')?.textContent, steps: $('steps')?.textContent, map: $('map')?.textContent})})()",
  returnByValue: true,
});
await sleep(1000);
const clearedAfterWait = await command("Runtime.evaluate", {
  expression: "JSON.stringify({selection: $('mapSelection')?.textContent, selectionEnabled: !$('useMapSelection')?.disabled, answer: $('answer')?.textContent, steps: $('steps')?.textContent, map: $('map')?.textContent})",
  returnByValue: true,
});
const clearSnapshot = JSON.parse(clearedAfterWait.result.result.value);
if (!clearSnapshot.selection.includes("点击地图要素后") || clearSnapshot.selectionEnabled) {
  throw new Error("清空对话没有清除地图选区");
}
if (clearSnapshot.answer || clearSnapshot.steps || clearSnapshot.map) {
  throw new Error("清空对话没有清除工作区结果");
}
socket.close();
