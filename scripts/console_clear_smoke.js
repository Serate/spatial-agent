const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const consoleUrl = process.env.CONSOLE_URL || "http://127.0.0.1:8088/";
const pages = await (await fetch("http://127.0.0.1:9222/json/list")).json();
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
await sleep(700);
const result = await command("Runtime.evaluate", {
  expression: "(()=>{ $('answer').textContent='旧分析结论'; $('steps').textContent='旧执行步骤'; selectedSpatialContext={admin_name:'洪山区'}; $('mapSelection').textContent='已选中：洪山区'; $('useMapSelection').disabled=false; $('clearChat').click(); return JSON.stringify({answer:$('answer').textContent,steps:$('steps').textContent,selection:$('mapSelection').textContent,selectionEnabled:!$('useMapSelection').disabled})})()",
  returnByValue: true,
});
if (result.result.exceptionDetails) {
  throw new Error(result.result.exceptionDetails.exception?.description || "clear action failed");
}
const snapshot = JSON.parse(result.result.result.value);
console.log(JSON.stringify(snapshot));
if (snapshot.answer || snapshot.steps || !snapshot.selection.includes("点击地图要素后") || snapshot.selectionEnabled) {
  throw new Error("清空对话没有清除当前工作区");
}
socket.close();
