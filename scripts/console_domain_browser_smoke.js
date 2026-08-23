/* Dynamic multi-Domain Console browser smoke. Requires the usual Chrome CDP page. */

import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
if (!source.includes('id="domain"') || !source.includes("nativeFetch('/domains')")) {
  throw new Error("Console 没有动态 Domain 目录入口");
}
if (/<option[^>]+value=["'](?:gis|text)["']/i.test(source)) {
  throw new Error("Console Shell 不应硬编码 GIS/Text Domain 选项");
}
for (const seam of ["domainPath('/capabilities'", "domainPath('/workflows'", "domainPath('/actions'", "domainPath('/sessions", "domainPath('/runs"]) {
  if (!source.includes(seam)) throw new Error(`Console 缺少领域化路由 seam：${seam}`);
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const cdpBase = process.env.CDP_URL || "http://127.0.0.1:9222";
const consoleUrl = process.env.CONSOLE_URL || "http://127.0.0.1:8088/";

const pagesResponse = await fetch(`${cdpBase}/json/list`);
if (!pagesResponse.ok) throw new Error(`无法连接 Chrome CDP：HTTP ${pagesResponse.status}`);
const pages = await pagesResponse.json();
const page = pages.find(item => item.type === "page");
if (!page) throw new Error("Chrome CDP 没有可用页面");

const socket = new WebSocket(page.webSocketDebuggerUrl);
let nextId = 0;
const pending = new Map();
socket.onmessage = event => {
  const message = JSON.parse(event.data);
  const resolver = pending.get(message.id);
  if (resolver) {
    pending.delete(message.id);
    resolver(message);
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
await new Promise((resolve, reject) => {
  socket.onopen = resolve;
  socket.onerror = () => reject(new Error("Chrome CDP WebSocket 连接失败"));
});
await command("Page.enable");
await command("Runtime.enable");
await command("Network.enable");
await command("Network.setCacheDisabled", {cacheDisabled: true});

function installDomainSmokeMock() {
  try { localStorage.removeItem("spatial-agent.console.domain"); } catch (error) { /* isolated fixture */ }
  const state = window.__domainSmoke = {requests: [], runCount: 0};
  const json = (data, status = 200) => new Response(JSON.stringify(data), {
    status,
    headers: {"Content-Type": "application/json"},
  });
  const runResult = (domainId, runId, request) => ({
    schema_version: "spatial-agent.run.v1",
    run_id: runId,
    domain_id: domainId,
    session_id: `${domainId}-session`,
    request,
    status: "COMPLETED",
    answer: `${domainId} completed`,
    artifact_ref: `legacy/private/${runId}.json`,
    trace_summary: [`${domainId} runtime completed`],
    result: {
      schema_version: "spatial-agent.result-envelope.v1",
      type: "direct_answer",
      title: `${domainId} result`,
      summary: `${domainId} generic result`,
      workspace: {
        schema_version: "spatial-agent.workspace.v1",
        registered_type: "direct_answer",
        primary_panel: "summary",
        common_panels: [],
        panels: ["summary"],
        view_specs: [{id: "summary", renderer: "generic", title: "通用结果", schema_version: "spatial-agent.view.v1"}],
      },
      views: {
        schema_version: "spatial-agent.views.v1",
        panels: {
          summary: {
            schema_version: "spatial-agent.view.v1",
            view_schema_version: "spatial-agent.view.v1",
            kind: "generic",
            title: "通用结果",
            rows: [{label: "Domain", value: domainId}, {label: "Request", value: request}],
          },
        },
      },
      runtime_context: {domain_id: domainId},
      artifacts: {
        run: {
          schema_version: "spatial-agent.artifact-reference.v1",
          available: true,
          kind: "run",
          ref: `${runId}.json`,
          access: {transport: "http", method: "GET", path: `/domains/${domainId}/artifacts/runs/${runId}.json`},
        },
      },
    },
  });
  window.fetch = async (input, init = {}) => {
    const method = String(init.method || "GET").toUpperCase();
    const target = new URL(typeof input === "string" ? input : input.url, location.href);
    const url = target.pathname + target.search;
    let body = {};
    try { body = typeof init.body === "string" && init.body ? JSON.parse(init.body) : {}; } catch (error) { body = {}; }
    state.requests.push({url, method, body});
    if (target.pathname === "/health") return json({capabilities: {live_llm_configured: true, live_llm_network: true}});
    if (target.pathname === "/domains") return json({
      schema_version: "spatial-agent.domain-runtime-host.v1",
      legacy_domain_id: "gis",
      domain_ids: ["gis", "text"],
      domains: [
        {id: "gis", label: "空间能力", description: "fixture domain one"},
        {id: "text", label: "文本能力", description: "fixture domain two"},
      ],
    });
    const match = target.pathname.match(/^\/domains\/([^/]+)(\/.*)?$/);
    if (!match) return json({detail: {code: "not_found", message: `mock route missing: ${url}`}}, 404);
    const domainId = decodeURIComponent(match[1]);
    const tail = match[2] || "";
    if (!["gis", "text"].includes(domainId)) return json({detail: {code: "unknown_domain", message: `unknown_domain: ${domainId}`}}, 404);
    if (tail === "/capabilities") return json({domain_id: domainId, capabilities: [], actions: {actions: []}});
    if (tail === "/capabilities/runtime") return json({domain_id: domainId, status: "ready", runtime: {fixture: true}});
    if (tail === "/workflows") return json({domain_id: domainId, templates: {}});
    if (tail === "/actions") return json({domain_id: domainId, actions: []});
    if (tail === "/sessions" && method === "POST") return json({session_id: `${domainId}-session`, display_name: "对话1", domain_id: domainId});
    if (tail === "/sessions" && method === "GET") return json({domain_id: domainId, sessions: domainId === "gis" ? [] : [{session_id: "text-session", display_name: "对话1", domain_id: domainId}]});
    if (/^\/sessions\/[^/]+\/runs$/.test(tail)) return json({domain_id: domainId, runs: []});
    if (/^\/sessions\/[^/]+\/clear$/.test(tail)) return json({status: "cleared", domain_id: domainId});
    if (/^\/sessions\/[^/]+$/.test(tail) && method === "DELETE") return json({status: "deleted", domain_id: domainId});
    if (tail === "/runs" && method === "GET") return json({domain_id: domainId, runs: []});
    if (tail === "/metrics") return json({domain_id: domainId, run_count: 0, total_tokens: 0, actions: {count: 0}});
    if (tail === "/action-executions") return json({domain_id: domainId, actions: []});
    if (tail === "/runs/async" && method === "POST") {
      if (String(body.request || "").includes("mismatch")) return json({detail: {code: "domain_mismatch", message: "domain_mismatch: URL 与请求领域不一致"}}, 409);
      if (String(body.request || "").includes("unknown")) return json({detail: {code: "unknown_domain", message: "unknown_domain: requested domain is unavailable"}}, 404);
      const runId = `${domainId}-run-${++state.runCount}`;
      state[runId] = {domainId, request: body.request};
      return json({run_id: runId, domain_id: domainId, status: "QUEUED"}, 202);
    }
    const runMatch = tail.match(/^\/runs\/([^/]+)$/);
    if (runMatch && method === "GET") {
      const runId = decodeURIComponent(runMatch[1]);
      const item = state[runId] || {domainId, request: "restored"};
      return json(runResult(item.domainId, runId, item.request));
    }
    return json({detail: {code: "not_found", message: `mock route missing: ${url}`}}, 404);
  };
}

await command("Page.addScriptToEvaluateOnNewDocument", {source: `(${installDomainSmokeMock.toString()})();`});
await command("Page.navigate", {url: consoleUrl});

const evaluate = async expression => {
  const result = await command("Runtime.evaluate", {expression, awaitPromise: true, returnByValue: true});
  if (result.result?.exceptionDetails) throw new Error(result.result.exceptionDetails.exception?.description || "浏览器脚本执行失败");
  return result.result?.result?.value;
};
for (let attempt = 0; attempt < 100; attempt++) {
  const ready = await evaluate("Boolean(window.__consoleBootstrapReady && window.__consoleDomainReady)");
  if (ready) break;
  await sleep(100);
  if (attempt === 99) throw new Error("Console Domain bootstrap 未就绪");
}

const snapshotRaw = await evaluate(`(async()=>{
  const waitReady=async()=>{for(let i=0;i<100&&!window.__consoleDomainReady;i++) await new Promise(resolve=>setTimeout(resolve,20));};
  const initial={
    options:[...$('domain').options].map(option=>({value:option.value,label:option.textContent})),
    domain:$('domain').value,
    session:$('session').value,
  };
  $('answer').textContent='STALE WORKSPACE';
  $('genericResult').textContent='STALE GENERIC';
  $('map').textContent='STALE MAP';
  const gisRun=sendChat('gis async switch test');
  for(let i=0;i<100&&!window.__domainSmoke.requests.some(item=>item.url==='/domains/gis/runs/async');i++) await new Promise(resolve=>setTimeout(resolve,10));
  $('domain').value='text';
  $('domain').dispatchEvent(new Event('change'));
  await waitReady();
  const reset={answer:$('answer').textContent,generic:$('genericResult').textContent,map:$('map').textContent,session:$('session').value,context:rendererRegistry.context()};
  await gisRun;
  const pollUrls=window.__domainSmoke.requests.filter(item=>item.method==='GET'&&item.url.includes('/runs/gis-run-')).map(item=>item.url);
  await sendChat('text generic result');
  const generic={visible:Boolean(document.querySelector('.generic-result.is-visible')),text:$('genericResult').textContent,artifact:[...document.querySelectorAll('#links a')].map(link=>link.getAttribute('href')).find(value=>value&&value.includes('/artifacts/runs/'))||''};
  await sendChat('mismatch fixture');
  const mismatch=$('error').textContent;
  await sendChat('unknown fixture');
  const unknown=$('error').textContent;
  return JSON.stringify({initial,reset,pollUrls,generic,mismatch,unknown,requests:window.__domainSmoke.requests});
})()`);
const snapshot = JSON.parse(snapshotRaw || "{}");

if (snapshot.initial?.options?.length !== 3 || snapshot.initial.options[0].value !== "auto" || snapshot.initial.options[1].value !== "gis" || snapshot.initial.options[2].value !== "text") {
  throw new Error(`动态 Domain 下拉不正确：${JSON.stringify(snapshot.initial)}`);
}
if (snapshot.initial.session !== "gis-session" || snapshot.reset?.session !== "text-session") {
  throw new Error(`会话没有按 Domain 隔离/创建：${JSON.stringify({initial: snapshot.initial, reset: snapshot.reset})}`);
}
if (snapshot.reset.answer || snapshot.reset.generic || snapshot.reset.map || Object.keys(snapshot.reset.context || {}).length) {
  throw new Error(`切换 Domain 未清空 workspace/selection：${JSON.stringify(snapshot.reset)}`);
}
if (!snapshot.pollUrls.some(url => url.startsWith("/domains/gis/runs/gis-run-")) || snapshot.pollUrls.some(url => url.startsWith("/domains/text/runs/gis-run-"))) {
  throw new Error(`异步轮询没有绑定提交时 Domain：${JSON.stringify(snapshot.pollUrls)}`);
}
if (!snapshot.generic?.visible || !snapshot.generic.text.includes("text") || !snapshot.generic.text.includes("通用结果")) {
  throw new Error(`Text 结果没有使用通用 renderer：${JSON.stringify(snapshot.generic)}`);
}
if (!snapshot.generic.artifact.startsWith("/domains/text/artifacts/runs/text-run-")) {
  throw new Error(`Console 没有优先消费 structured artifact access.path：${JSON.stringify(snapshot.generic)}`);
}
if (!snapshot.mismatch.includes("domain_mismatch") || !snapshot.unknown.includes("unknown_domain")) {
  throw new Error(`领域错误没有清晰显示：${JSON.stringify({mismatch: snapshot.mismatch, unknown: snapshot.unknown})}`);
}
const urls = snapshot.requests.map(item => item.url);
for (const required of [
  "/domains/gis/capabilities?planner=rule&backend=memory",
  "/domains/gis/workflows",
  "/domains/gis/actions?planner=rule&backend=memory",
  "/domains/gis/sessions",
  "/domains/text/capabilities?planner=rule&backend=memory",
  "/domains/text/workflows",
  "/domains/text/actions?planner=rule&backend=memory",
  "/domains/text/sessions?limit=50",
  "/domains/text/runs/async",
]) {
  if (!urls.includes(required)) throw new Error(`缺少领域化请求：${required}`);
}

console.log(JSON.stringify({domains: snapshot.initial.options, reset: snapshot.reset, pollUrls: snapshot.pollUrls, generic: snapshot.generic, errors: {mismatch: snapshot.mismatch, unknown: snapshot.unknown}}));
socket.close();
process.exit(0);
