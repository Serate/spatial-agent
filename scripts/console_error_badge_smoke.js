/*
 * M79.2 browser smoke: structured error_category badges render in the result
 * zone (not raw strings), and result panels show actionable empty hints.
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
  }, 20000);
});
await new Promise(resolve => { socket.onopen = resolve; });
await command("Page.enable");
await command("Runtime.enable");
await command("Page.navigate", {url: consoleUrl});
for (let attempt = 0; attempt < 60; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "typeof $ === 'function' && typeof renderRun === 'function' && typeof errorCategoryBadge === 'function'",
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

// 工具失败：error_category=tool → 徽标「工具执行错误」+ 原始错误文本保留。
const toolSnapshot = await evaluate(`(()=>{
  renderRun({run_id:'badge-tool',status:'FAILED',request:'测试',error:'模拟工具后端失败',error_category:'tool',steps:[{tool:'get_raster_statistics',status:'FAILED',error:'模拟工具后端失败'}]});
  return JSON.stringify({
    badge: document.querySelector('#error .error-category')?.textContent || '',
    badgeClass: document.querySelector('#error .error-category')?.className || '',
    text: document.querySelector('#error')?.textContent || ''
  });
})()`, true);
const tool = JSON.parse(toolSnapshot || "{}");
if (tool.badge !== "工具执行错误" || !tool.badgeClass.includes('error-category tool')) {
  throw new Error(`工具失败未渲染 error_category=tool 徽标：${toolSnapshot}`);
}
if (!tool.text.includes("模拟工具后端失败")) {
  throw new Error(`错误原始文本丢失：${toolSnapshot}`);
}

// 请求拒绝：error_category=rejected → 徽标「请求已拒绝」。
const rejectedSnapshot = await evaluate(`(()=>{
  renderRun({run_id:'badge-rejected',status:'REJECTED',request:'测试',error:'该请求不在当前能力范围内',error_category:'rejected',steps:[]});
  return JSON.stringify({
    badge: document.querySelector('#error .error-category')?.textContent || '',
    badgeClass: document.querySelector('#error .error-category')?.className || ''
  });
})()`, true);
const rejected = JSON.parse(rejectedSnapshot || "{}");
if (rejected.badge !== "请求已拒绝" || !rejected.badgeClass.includes('error-category rejected')) {
  throw new Error(`拒绝运行未渲染 error_category=rejected 徽标：${rejectedSnapshot}`);
}

// 成功结果：不渲染错误徽标，也不出现错误块。
const okSnapshot = await evaluate(`(()=>{
  renderRun({run_id:'badge-ok',status:'COMPLETED',request:'你好',answer:'你好',steps:[]});
  return JSON.stringify({error: document.querySelector('#error')?.textContent || '', badge: Boolean(document.querySelector('#error .error-category'))});
})()`, true);
const ok = JSON.parse(okSnapshot || "{}");
if (ok.badge || ok.error !== '') {
  throw new Error(`成功结果不应渲染错误徽标：${okSnapshot}`);
}

// 空态收敛：直接回答结果不显示栅格/健康面板的「等待」占位；比较面板显示可操作提示。
const placeholderSnapshot = await evaluate(`(()=>{
  resetConversationView();
  return JSON.stringify({
    raster: document.querySelector('#rasterStats')?.textContent || '',
    compare: document.querySelector('#compareResults')?.textContent || '',
    regionCompare: document.querySelector('#regionCompareResults')?.textContent || ''
  });
})()`, true);
const placeholders = JSON.parse(placeholderSnapshot || "{}");
if (placeholders.raster.includes('等待')) {
  throw new Error(`面板仍使用误导性「等待」占位：${placeholderSnapshot}`);
}
if (!placeholders.compare.includes('对比') || !placeholders.regionCompare.includes('多区域对比')) {
  throw new Error(`比较面板缺少可操作提示：${placeholderSnapshot}`);
}

console.log(JSON.stringify({tool, rejected, ok, placeholders}));
socket.close();
process.exit(0);
