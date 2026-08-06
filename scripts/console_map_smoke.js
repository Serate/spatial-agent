/* Browser smoke check for the interactive console map. Requires Chrome started with CDP. */

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
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
await command("Page.navigate", {url: "http://127.0.0.1:8088/"});
await sleep(1500);
await command("Runtime.evaluate", {expression: "sendChat('分析洪山区建设适宜性，坡度不超过20度')"});
await sleep(7000);
const result = await command("Runtime.evaluate", {
  expression: `JSON.stringify({
    leaflet: Boolean(document.querySelector('#leafletMap')),
    leafletPaths: document.querySelectorAll('.leaflet-overlay-pane path').length,
    svgPaths: document.querySelectorAll('#map svg path').length,
    empty: Boolean(document.querySelector('#map .map-empty')),
    status: document.querySelector('#status')?.textContent
  })`,
  returnByValue: true,
});
const snapshot = JSON.parse(result.result.result.value);
console.log(JSON.stringify(snapshot));
if (snapshot.leafletPaths < 1 && snapshot.svgPaths < 1) {
  throw new Error("空间预览没有生成任何矢量图层");
}
socket.close();
