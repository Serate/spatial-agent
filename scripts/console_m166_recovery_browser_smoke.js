/*
 * M166 browser smoke: recoverable timeout -> recover -> completed.
 * Requires Chrome started with scripts/console_cdp_start.ps1.
 */
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const consoleUrl = process.env.CONSOLE_URL || "http://127.0.0.1:8088/";
const cdpUrl = process.env.CDP_URL || "http://127.0.0.1:9222";
const pages = await (await fetch(`${cdpUrl}/json/list`)).json();
const page = pages.find(item => item.type === "page");
if (!page) throw new Error("Chrome CDP page was not found");

const socket = new WebSocket(page.webSocketDebuggerUrl);
process.on('exit', () => { try { socket.close(); } catch {} });
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
  }, 20000);
});
await new Promise(resolve => { socket.onopen = resolve; });
await command("Page.enable");
await command("Runtime.enable");
await command("Page.navigate", {url: consoleUrl});

for (let attempt = 0; attempt < 80; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "typeof $ === 'function' && typeof renderRun === 'function' && $('send')",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 79) throw new Error("Console 页面脚本未就绪");
}

const result = await command("Runtime.evaluate", {
  expression: `(async()=>{
    $('planner').value='rule';
    $('backend').value='memory';
    const response=await nativeFetch('/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request:'查询洪山区行政区边界',planner:'rule',backend:'memory',session_id:'m166-browser-recovery-'+Date.now(),timeout_seconds:0.001,export_artifact:true})});
    const failed=await response.json();
    if(failed.status!=='TIMED_OUT') throw new Error('timeout fixture did not reach TIMED_OUT');
    renderRun(failed);
    const initialState=document.querySelector('[data-selection-state]')?.getAttribute('data-selection-state')||'';
    const recover=document.querySelector('[data-selection-action="recover"]');
    if(!recover) throw new Error('recover 动作未渲染');
    recover.click();
    let finalState='';
    let finalStatus='';
    for(let attempt=0;attempt<80;attempt++){
      finalState=document.querySelector('[data-selection-state]')?.getAttribute('data-selection-state')||'';
      finalStatus=$('status')?.textContent||'';
      if(finalState==='completed') break;
      await new Promise(resolve=>setTimeout(resolve,250));
    }
    return JSON.stringify({initialState,finalState,finalStatus,card:document.querySelector('.selection-interaction-card')?.textContent||''});
  })()`,
  awaitPromise: true,
  returnByValue: true,
});
if (result.result.exceptionDetails) {
  throw new Error(JSON.stringify(result.result.exceptionDetails));
}
const snapshot = JSON.parse(result.result.result.value);
console.log(JSON.stringify(snapshot));
if (snapshot.initialState !== "recoverable" || snapshot.finalState !== "completed") {
  throw new Error(`recovery interaction was not completed: ${JSON.stringify(snapshot)}`);
}
socket.close();
process.exit(0);
