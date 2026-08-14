/*
 * M79 browser smoke: lineage navigation opens the original run detail
 * (history item / linked message / comparison row) without re-invoking the
 * model. A "no re-execution" violation is observable as an increasing
 * /metrics run_count (each run writes a durable artifact) or a new run_id.
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
    expression: "typeof $ === 'function' && typeof sendChat === 'function' && typeof openRunDetail === 'function'",
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

const runCount = () => evaluate("(async()=>{ const r=await (await fetch('/metrics')).json(); return r.run_count||0; })()", true);
const createRun = request => evaluate(`(async()=>{ const response=await nativeFetch('/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request:${JSON.stringify(request)},planner:'rule',backend:'memory',session_id:'lineage-smoke',export_artifact:true,export_geojson:true})}); if(!response.ok) throw new Error(await response.text()); return response.json(); })()`, true);

const countBefore = await runCount();
const runA = await createRun("查询DEM栅格元数据");
const runB = await createRun("你好");
const countCreated = await runCount();
if (countCreated !== countBefore + 2) {
  throw new Error(`创建两个运行后 run_count 应为 ${countBefore + 2}，实际 ${countCreated}`);
}

// 历史列表：主按钮打开详情，副按钮保留重跑，且不重新执行。
await evaluate("loadHistory()");
await sleep(600);
const historySnapshot = await evaluate(`JSON.stringify([...document.querySelectorAll('#historyList .history-item')].map(item=>({open:item.querySelector('[data-history-run]')?.getAttribute('data-history-run')||'',rerun:Boolean(item.querySelector('.history-rerun'))})))`, true);
const historyItems = JSON.parse(historySnapshot || "[]");
if (historyItems.length < 2) throw new Error(`历史列表应至少 2 项，实际 ${historyItems.length}`);
for (const item of historyItems) {
  if (!item.open) throw new Error(`历史项缺少 data-history-run 导航：${JSON.stringify(item)}`);
  if (!item.rerun) throw new Error(`历史项缺少「重跑」副按钮：${JSON.stringify(item)}`);
}
const firstRunId = historyItems[0].open;
await evaluate(`document.querySelector('#historyList [data-history-run]')?.click()`);
await sleep(800);
const afterOpen = await evaluate(`JSON.stringify({status:$('status')?.textContent,title:$('title')?.textContent,linked:Boolean(document.querySelector('#messages .msg-linked')),linkedRunId:document.querySelector('#messages .msg-linked')?.dataset.runId||''})`, true);
const opened = JSON.parse(afterOpen || "{}");
if (!opened.linked || opened.linkedRunId !== firstRunId) {
  throw new Error(`打开历史详情后未生成可点击的原始运行消息：${afterOpen}`);
}
if (!opened.title || opened.status === "失败") {
  throw new Error(`历史详情渲染异常：${afterOpen}`);
}
const countAfterOpen = await runCount();
if (countAfterOpen !== countCreated) {
  throw new Error(`打开历史详情不应重新执行模型：run_count ${countCreated} -> ${countAfterOpen}`);
}

// 可点击消息：再次打开同一运行详情，run_count 不变。
await evaluate(`document.querySelector('#messages .msg-linked')?.click()`);
await sleep(800);
const afterMessageClick = await evaluate(`JSON.stringify({status:$('status')?.textContent,runId:$('lineageEvidence')?.textContent.match(/运行 ID：([0-9a-zA-Z-]+)/)?.[1]||''})`, true);
const reopened = JSON.parse(afterMessageClick || "{}");
if (reopened.runId !== firstRunId) {
  throw new Error(`点击可点击消息未回到原运行详情：${afterMessageClick}`);
}
const countAfterMessageClick = await runCount();
if (countAfterMessageClick !== countCreated) {
  throw new Error(`点击可点击消息不应重新执行模型：run_count ${countCreated} -> ${countAfterMessageClick}`);
}

// 比较结果：每行携带 run_id 详情入口，点击打开子运行详情且不重跑。
await evaluate(`(()=>{ $('compareThresholds').value='15,20'; $('compareButton').click(); })()`);
let compareReady = false;
for (let attempt = 0; attempt < 40; attempt++) {
  const ready = await evaluate("Boolean(document.querySelector('#compareResults .compare-detail'))", true);
  if (ready) { compareReady = true; break; }
  await sleep(250);
}
if (!compareReady) throw new Error("比较结果没有渲染详情入口");
const compareSnapshot = await evaluate(`JSON.stringify([...document.querySelectorAll('#compareResults .compare-detail')].map(button=>button.getAttribute('data-run-id')))`, true);
const compareRunIds = JSON.parse(compareSnapshot || "[]");
if (compareRunIds.length < 2 || compareRunIds.some(id => !id)) {
  throw new Error(`比较详情入口缺少 run_id：${compareSnapshot}`);
}
await evaluate(`document.querySelector('#compareResults .compare-detail')?.click()`);
await sleep(800);
const countAfterCompare = await runCount();
if (countAfterCompare !== countCreated) {
  throw new Error(`打开比较详情不应重新执行模型：run_count ${countCreated} -> ${countAfterCompare}`);
}
const afterCompareOpen = await evaluate(`JSON.stringify({runId:$('lineageEvidence')?.textContent.match(/运行 ID：([0-9a-zA-Z-]+)/)?.[1]||'',linked:Boolean(document.querySelector('#messages .msg-linked'))})`, true);
const compared = JSON.parse(afterCompareOpen || "{}");
if (!compareRunIds.includes(compared.runId)) {
  throw new Error(`比较详情打开的 run_id 不在子运行列表中：${afterCompareOpen}`);
}
if (!compared.linked) throw new Error(`比较详情打开后应生成可点击的原始运行消息：${afterCompareOpen}`);

console.log(JSON.stringify({
  countBefore,
  countCreated,
  countAfterOpen,
  countAfterMessageClick,
  countAfterCompare,
  firstRunId,
  historyItems: historyItems.length,
  compareRunIds,
  finalRunId: compared.runId,
}));
socket.close();
