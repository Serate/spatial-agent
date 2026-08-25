/* M283-D browser smoke for the shared user-facing result projection. */
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
  if (resolve) { pending.delete(message.id); resolve(message); }
};
const command = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++nextId;
  pending.set(id, resolve);
  socket.send(JSON.stringify({id, method, params}));
  setTimeout(() => { if (pending.delete(id)) reject(new Error(`CDP timeout: ${method}`)); }, 15000);
});
await new Promise(resolve => { socket.onopen = resolve; });
await command("Page.enable");
await command("Runtime.enable");
const cacheBustUrl = consoleUrl + (consoleUrl.includes("?") ? "&" : "?") + "m283=projection";
await command("Page.navigate", {url: cacheBustUrl});
for (let attempt = 0; attempt < 60; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "Boolean(window.ConsoleResultProjection && document.querySelector('#answerProjection'))",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 59) {
    const debug = await command("Runtime.evaluate", {expression: "JSON.stringify({url:location.href,projection:typeof window.ConsoleResultProjection,answerProjection:Boolean(document.querySelector('#answerProjection')),scripts:[...document.scripts].map(item=>item.src).slice(-5),error:document.querySelector('#error')?.textContent||''})", returnByValue: true});
    throw new Error("结果 projection 未加载：" + (debug.result?.result?.value || "unknown"));
  }
}
const evaluated = await command("Runtime.evaluate", {
  expression: `(()=>{
    const fixture={status:'COMPLETED',runtime_context:{schema_version:'spatial-agent.composite-request-context.v2'},plan:{steps:[{id:'hidden',tool:'hidden_tool'}]},result:{type:'composite_result',view:{schema_version:'spatial-agent.composite-view.v1',answer:{summary:'浏览器投影已形成结论',key_findings:['关键发现']},views:[{view_id:'metrics',kind:'metrics',state:'ready'}],evidence:{available:true}}}};
    const model=window.ConsoleResultProjection.normalize(fixture);
    document.querySelector('#answer').textContent=model.answer.summary;
    const target=document.querySelector('#answerProjection');
    target.innerHTML=window.ConsoleResultProjection.render(model);
    target.hidden=false;
    return JSON.stringify({summary:document.querySelector('#answer').textContent,projection:Boolean(target.querySelector('[data-projection-schema]')),phases:target.querySelectorAll('.result-phase').length,findings:target.textContent.includes('关键发现'),hiddenTool:target.textContent.includes('hidden_tool')});
  })()`,
  awaitPromise: true,
  returnByValue: true,
});
if (evaluated.result?.exceptionDetails) throw new Error(evaluated.result.exceptionDetails.exception?.description || "projection browser evaluation failed");
const snapshot = JSON.parse(evaluated.result.result.value);
console.log(JSON.stringify(snapshot));
if (!snapshot.projection || snapshot.phases !== 6 || !snapshot.findings || snapshot.hiddenTool) throw new Error("结果 projection 浏览器展示不符合契约");
socket.close();
