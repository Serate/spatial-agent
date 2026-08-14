/*
 * M79.5.2 browser smoke: the road-distance comparison control renders a
 * monotonicity badge and a result table after a real constrained comparison.
 * Requires Chrome started with CDP (scripts/console_cdp_start.ps1).
 */

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
  }, 30000);
});
await new Promise(resolve => { socket.onopen = resolve; });
await command("Page.enable");
await command("Runtime.enable");
await command("Page.navigate", {url: consoleUrl});
for (let attempt = 0; attempt < 60; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "typeof $ === 'function' && typeof compareConstrained === 'function' && !!$('constrainedCompareButton')",
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
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || result.exceptionDetails.exception?.description || "browser evaluation failed");
  const value = result.result?.result?.value;
  if (needsValue && value === undefined) throw new Error(`browser evaluation returned no value: ${JSON.stringify(result)}`);
  return value;
};

// 使用 rule planner + local backend（容器内有完整数据卷），点击「道路距离对比」。
await evaluate(`(()=>{
  if ($('planner')) $('planner').value = 'rule';
  if ($('backend')) $('backend').value = 'local';
  $('constrainedCompareRegion').value = '洪山区';
  $('constrainedSlope').value = 15;
  $('constrainedRoadDistances').value = '200,500,1000';
  $('constrainedCompareButton').click();
  return true;
})()`);

let snapshot = "";
for (let attempt = 0; attempt < 60; attempt++) {
  snapshot = await evaluate(`JSON.stringify({
    text: document.querySelector('#constrainedCompareResults')?.textContent || '',
    rows: document.querySelectorAll('#constrainedCompareResults tbody tr').length,
    badgeOk: !!document.querySelector('#constrainedCompareResults .monotonic-badge.ok'),
    badgeFail: !!document.querySelector('#constrainedCompareResults .monotonic-badge.fail')
  })`, true);
  const state = JSON.parse(snapshot || "{}");
  if (state.rows >= 3 && (state.badgeOk || state.badgeFail)) break;
  await sleep(500);
  if (attempt === 59) throw new Error(`约束对比结果未渲染：${snapshot}`);
}

const state = JSON.parse(snapshot || "{}");
if (state.rows < 3) throw new Error(`约束对比表格行数不足：${snapshot}`);
if (!state.badgeOk) throw new Error(`约束对比未显示单调性通过徽标（rows=${state.rows} badgeOk=${state.badgeOk}）: ${snapshot}`);
if (!state.text.includes("200") || !state.text.includes("1,000")) throw new Error(`约束对比表格缺少道路距离值：${snapshot}`);
if (!state.text.includes("满足道路距离约束候选单调不减")) throw new Error(`约束对比缺少单调性说明文本：${snapshot}`);

console.log(`constrained smoke PASS: rows=${state.rows} monotonicBadge=true`);
socket.close();
