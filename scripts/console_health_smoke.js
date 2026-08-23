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
    expression: "document.readyState==='complete' && typeof $ === 'function' && typeof sendChat === 'function' && $('prompt') && $('status')?.textContent==='待机'",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 59) throw new Error("Console 页面脚本未就绪");
}
const result = await command("Runtime.evaluate", {
  expression: "(async()=>{ $('backend').value='memory'; if(typeof newSession==='function') await newSession(); await sendChat('检查武汉空间数据质量'); for(let i=0;i<50;i++){ await new Promise(resolve=>setTimeout(resolve,200)); if($('status')?.textContent==='已完成') break; } return JSON.stringify({panel:Boolean(document.querySelector('.generic-result.is-visible')), text:$('genericResult')?.textContent||'', output:document.querySelector('.generic-result h3')?.textContent||'', tool:(document.querySelector('.step-tool')?.textContent||''), status:$('status')?.textContent||''}); })()",
  awaitPromise: true,
  returnByValue: true,
});
if (result.result.exceptionDetails) {
  throw new Error(JSON.stringify(result.result.exceptionDetails));
}
const snapshot = JSON.parse(result.result.result.value);
console.log(JSON.stringify(snapshot));
if (!snapshot.panel || snapshot.output !== "结构化结果" || !snapshot.text.includes("整体状态") || !snapshot.text.includes("核心数据") || !snapshot.text.includes("admin_areas") || snapshot.tool !== "get_dataset_health_report") {
  throw new Error("数据健康结果没有通过统一动态结果视图展示");
}
socket.close();
process.exit(0);
