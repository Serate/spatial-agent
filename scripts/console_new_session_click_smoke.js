/*
 * Regression smoke for the real New Session button.
 * It creates one temporary session in the GIS Domain and removes that exact
 * session after the assertion; it does not clear existing conversations.
 * Requires Chrome started with scripts/console_cdp_start.ps1.
 */
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
await command("Emulation.setDeviceMetricsOverride", {width: 1440, height: 900, deviceScaleFactor: 1, mobile: false});
await command("Page.navigate", {url: consoleUrl});
for (let attempt = 0; attempt < 120; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "typeof $ === 'function' && typeof newSession === 'function' && Boolean(window.__consoleBootstrapReady)",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 119) throw new Error("Console 页面脚本未就绪");
}
const result = await command("Runtime.evaluate", {
  expression: `(async()=>{
    const domain='gis';
    $('domain').value=domain;
    $('domain').dispatchEvent(new Event('change',{bubbles:true}));
    for(let attempt=0;attempt<120&&!window.__consoleDomainReady;attempt++) await new Promise(resolve=>setTimeout(resolve,250));
    if(!window.__consoleDomainReady) throw new Error('GIS 领域目录未就绪');
    const before=$('session').options.length;
    const beforeSelected=$('session').value;
    const oldConfirm=window.confirm;
    let created=null;
    try {
      window.confirm=()=>true;
      $('newSession').click();
      for(let attempt=0;attempt<120;attempt++) {
        if($('session').options.length>before && $('session').value!==beforeSelected) break;
        await new Promise(resolve=>setTimeout(resolve,100));
      }
      const after=$('session').options.length;
      const selected=$('session').value;
      if(after<=before || !selected || selected===beforeSelected) throw new Error('点击新建会话后下拉选项或当前选择未变化：disabled='+$('newSession').disabled+'，domain='+$('domain').value+'，ready='+window.__consoleDomainReady+'，before='+before+'，after='+after+'，error='+$('error').textContent);
      created=selected;
      return JSON.stringify({before,beforeSelected,after,selected,chatMeta:$('chatMeta').textContent});
    } finally {
      window.confirm=oldConfirm;
      if(created) {
        await nativeFetch('/domains/'+encodeURIComponent(domain)+'/sessions/'+encodeURIComponent(created),{method:'DELETE'}).catch(()=>{});
      }
    }
  })()`,
  awaitPromise: true,
  returnByValue: true,
});
if (result.result.exceptionDetails) throw new Error(result.result.exceptionDetails.exception?.description || "new session click failed");
console.log(result.result.result.value);
socket.close();
