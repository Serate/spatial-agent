/*
 * M166 browser smoke: facts_required -> provide_facts -> completed.
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
    expression: "typeof $ === 'function' && typeof sendChat === 'function' && $('workflow')?.options?.length > 1",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 79) throw new Error("Console 页面脚本或工作流目录未就绪");
}

const result = await command("Runtime.evaluate", {
  expression: `(async()=>{
    const sessionId='m166-facts-browser-'+Date.now();
    const sessionOption=document.createElement('option');
    sessionOption.value=sessionId;
    sessionOption.textContent='M166事实验收';
    $('session').append(sessionOption);
    $('session').value=sessionId;
    $('planner').value='rule';
    $('backend').value='memory';
    $('workflow').value='';
    $('workflow').dispatchEvent(new Event('change',{bubbles:true}));
    $('requireConfirmation').checked=false;
    await sendChat('分析空间数据');
    const initialState=document.querySelector('[data-selection-state]')?.getAttribute('data-selection-state')||'';
    const workflow=$('workflow');
    workflow.value='spatial_overview';
    workflow.dispatchEvent(new Event('change',{bubbles:true}));
    await new Promise(resolve=>setTimeout(resolve,100));
    const field=document.querySelector('[data-workflow-field="admin_name"]');
    if(!field) throw new Error('admin_name 工作流字段未渲染');
    field.value='洪山区';
    field.dispatchEvent(new Event('input',{bubbles:true}));
    field.dispatchEvent(new Event('change',{bubbles:true}));
    const action=document.querySelector('[data-selection-action="provide_facts"]');
    if(!action) throw new Error('provide_facts 动作未渲染');
    action.click();
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
if (snapshot.initialState !== "facts_required" || snapshot.finalState !== "completed") {
  throw new Error(`facts interaction was not completed: ${JSON.stringify(snapshot)}`);
}
socket.close();
process.exit(0);
