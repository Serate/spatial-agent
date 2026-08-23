/* Browser smoke check for conversation switching and result restoration. */

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const consoleUrl = process.env.CONSOLE_URL || "http://127.0.0.1:8088/";
const cdpUrl = process.env.CDP_URL || "http://127.0.0.1:9222";
const response = await fetch(`${cdpUrl}/json/list`);
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
for (let attempt = 0; attempt < 60; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "typeof $ === 'function' && typeof sendChat === 'function'",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 59) throw new Error("Console 页面脚本未就绪");
}

const evaluate = async (expression, needsValue = false) => {
  const result = await command("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || "browser evaluation failed");
  const value = result.result?.result?.value;
  if (needsValue && value === undefined) throw new Error(`browser evaluation returned no value: ${JSON.stringify(result)}`);
  return value;
};

const sessionA = await evaluate("(async()=>await (await fetch('/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json())()", true);
const sessionB = await evaluate("(async()=>await (await fetch('/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json())()", true);
const createRun = async (session, request, backend) => evaluate(`(async()=>{ const response=await fetch('/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request:${JSON.stringify(request)},planner:'rule',backend:${JSON.stringify(backend)},session_id:${JSON.stringify(session)},export_artifact:false,export_geojson:false})}); if(!response.ok) throw new Error(await response.text()); return response.json(); })()`, true);
await createRun(sessionA.session_id, '你好', 'memory');
await createRun(sessionB.session_id, '查询DEM栅格元数据', 'local');
await evaluate(`(async()=>{ await loadSessions(); $('session').value=${JSON.stringify(sessionA.session_id)}; await restoreSession(); })()`);
await evaluate(`(async()=>{ await loadSessions(); $('session').value=${JSON.stringify(sessionA.session_id)}; await restoreSession(); })()`);
await sleep(1000);

const snapshot = await evaluate(`JSON.stringify({
  selected: $('session').value,
  messages: [...document.querySelectorAll('#messages .bubble')].map(item => item.textContent),
  resultType: document.querySelector('#decisionMode')?.textContent,
  genericVisible: Boolean(document.querySelector('.generic-result.is-visible')),
  genericText: document.querySelector('#genericResult')?.textContent || ''
})`, true);
const result = JSON.parse(snapshot);
console.log(JSON.stringify(result));
if (result.selected !== sessionA.session_id) throw new Error("conversation selection was not restored");
if (!result.messages.some(item => item === '你好')) throw new Error("conversation user history was not restored");
if (!result.messages.some(item => item.includes('空间智能体'))) throw new Error("conversation assistant history was not restored");
if (!result.genericVisible || !result.genericText.includes('direct_answer')) throw new Error("selected conversation result was not restored into the unified result view");
if (result.genericText.includes('raster_metadata') || result.genericText.includes('get_raster_metadata')) throw new Error("result from another conversation leaked into the selected conversation");
socket.close();
process.exit(0);
