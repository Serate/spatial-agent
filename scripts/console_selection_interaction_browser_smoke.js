/*
 * M165/M166 browser smoke: the Console renders the domain-neutral selection
 * interaction projection and completes a real confirmation action.
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

for (let attempt = 0; attempt < 60; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "typeof $ === 'function' && typeof sendChat === 'function' && !!$('requireConfirmation')",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 59) throw new Error("Console 页面脚本未就绪");
}

const result = await command("Runtime.evaluate", {
  expression: `(async()=>{
    const sessionId='m166-selection-browser-'+Date.now();
    const sessionOption=document.createElement('option');
    sessionOption.value=sessionId;
    sessionOption.textContent='M166选择验收';
    $('session').append(sessionOption);
    $('session').value=sessionId;
    $('planner').value='rule';
    $('backend').value='memory';
    $('workflow').value='';
    $('workflow').dispatchEvent(new Event('change',{bubbles:true}));
    $('requireConfirmation').checked=true;
    await sendChat('查询DEM栅格元数据');
    const history=await (await fetch('/runs?limit=5')).json();
    const latest=history.runs?.[0];
    const detail=latest?.run_id
      ? await (await fetch('/runs/'+encodeURIComponent(latest.run_id)+'?planner=rule&backend=memory')).json()
      : {};
    const normalizedDetail=normalizeSelectionInteraction(detail);
    const initialState=document.querySelector('[data-selection-state]')?.getAttribute('data-selection-state')||'';
    const initialCard=document.querySelector('.selection-interaction-card')?.textContent||'';
    const initialActions=[...document.querySelectorAll('[data-selection-action]')].map(item=>item.getAttribute('data-selection-action'));
    const confirm=document.querySelector('[data-selection-action="confirm"]');
    if(!confirm) throw new Error('confirm 动作未渲染');
    confirm.click();
    let finalState='';
    let finalStatus='';
    for(let attempt=0;attempt<80;attempt++){
      finalState=document.querySelector('[data-selection-state]')?.getAttribute('data-selection-state')||'';
      finalStatus=$('status')?.textContent||'';
      if(finalState==='completed') break;
      await new Promise(resolve=>setTimeout(resolve,250));
    }
    const snapshot={
      status:$('status')?.textContent||'',
      state:document.querySelector('[data-selection-state]')?.getAttribute('data-selection-state')||'',
      card:document.querySelector('.selection-interaction-card')?.textContent||'',
      actions:[...document.querySelectorAll('[data-selection-action]')].map(item=>item.getAttribute('data-selection-action')),
      initialState,
      initialCard,
      initialActions,
      finalState,
      finalStatus,
      detailStatus:detail.status||'',
      detailState:detail.result?.selection_interaction?.state||'',
      detailSchema:detail.result?.selection_interaction?.schema_version||'',
      moduleLoaded:Boolean(window.ConsoleSelectionInteraction),
      moduleVersion:window.ConsoleSelectionInteraction?.VERSION||'',
      normalizedState:normalizedDetail.state||'',
    };
    return JSON.stringify(snapshot);
  })()`,
  awaitPromise: true,
  returnByValue: true,
});
if (result.result.exceptionDetails) {
  throw new Error(JSON.stringify(result.result.exceptionDetails));
}
const snapshot = JSON.parse(result.result.result.value);
console.log(JSON.stringify(snapshot));
if (snapshot.initialState !== "confirmation_required" || snapshot.finalState !== "completed") {
  throw new Error(`selection interaction was not rendered: ${JSON.stringify(snapshot)}`);
}
if (!snapshot.initialActions.includes("confirm") || !snapshot.initialActions.includes("reject")) {
  throw new Error(`confirmation actions are missing: ${JSON.stringify(snapshot)}`);
}
if (!snapshot.initialCard.includes("下一步交互")) {
  throw new Error("selection interaction card is missing");
}
socket.close();
process.exit(0);
