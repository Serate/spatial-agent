/* M225 smart Domain routing browser smoke. Requires the usual offline Chrome CDP page. */

import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
for (const seam of ["/runs/auto", "domain_routing", "ConsoleActionHost.mount", "select_domain"]) {
  if (!source.includes(seam)) throw new Error(`Console 缺少智能领域路由 seam：${seam}`);
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

function installDomainRoutingMock() {
  let preserveFixtureState = false;
  try {
    localStorage.setItem("spatial-agent.console.domain", "auto");
    preserveFixtureState = localStorage.getItem("spatial-agent.domain-routing-smoke.preserve") === "1";
    if (!preserveFixtureState) {
      localStorage.removeItem("spatial-agent.console.auto-binding");
      localStorage.removeItem("spatial-agent.domain-routing-smoke.session.gis");
      localStorage.removeItem("spatial-agent.domain-routing-smoke.session.text");
    }
    localStorage.removeItem("spatial-agent.domain-routing-smoke.preserve");
  } catch (error) { /* isolated fixture */ }
  const state = window.__domainRoutingSmoke = {requests: [], runCount: 0, sessions: {}};
  if (preserveFixtureState) {
    for (const domainId of ["gis", "text"]) {
      const sessionId = localStorage.getItem(`spatial-agent.domain-routing-smoke.session.${domainId}`);
      if (sessionId) state.sessions[domainId] = sessionId;
    }
  }
  const json = (data, status = 200) => new Response(JSON.stringify(data), {
    status,
    headers: {"Content-Type": "application/json"},
  });
  const completed = (domainId, runId, request, sessionId) => ({
    schema_version: "spatial-agent.run.v1",
    run_id: runId,
    domain_id: domainId,
    session_id: sessionId,
    request,
    status: "COMPLETED",
    answer: `${domainId} completed: ${request}`,
    trace_summary: [`${domainId} runtime completed`],
    result: {
      schema_version: "spatial-agent.result-envelope.v1",
      type: "direct_answer",
      title: `${domainId} result`,
      summary: `${domainId} completed: ${request}`,
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
        panels: {summary: {schema_version: "spatial-agent.view.v1", view_schema_version: "spatial-agent.view.v1", kind: "generic", title: "通用结果", rows: [{label: "Domain", value: domainId}]}}
      },
      runtime_context: {domain_id: domainId},
    },
  });
  const queue = (domainId, request, sessionId) => {
    const runId = `${domainId}-run-${++state.runCount}`;
    state[runId] = {domainId, request, sessionId};
    state.sessions[domainId] = sessionId;
    try { localStorage.setItem(`spatial-agent.domain-routing-smoke.session.${domainId}`, sessionId); } catch (error) { /* fixture */ }
    return {run_id: runId, domain_id: domainId, session_id: sessionId, status: "QUEUED"};
  };
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
      domains: [
        {id: "gis", label: "空间能力", description: "fixture domain one"},
        {id: "text", label: "文本能力", description: "fixture domain two"},
      ],
    });
    if (target.pathname === "/runs/auto" && method === "POST") {
      if (body.domain_routing_decision_id === "route-override-gis") return json(queue("gis", body.request, body.session_id), 202);
      if (body.domain_routing_decision_id === "route-override-text") return json(queue("text", body.request, body.session_id), 202);
      if (String(body.request || "").includes("ambiguous")) return json({
        status: "NEEDS_CLARIFICATION",
        domain_routing: {
          decision_id: "route-ambiguous",
          status: "AMBIGUOUS",
          reason_code: "multiple_domains_matched",
          candidates: [
            {domain_id: "gis", label: "空间能力", capability_ids: ["boundary_lookup"]},
            {domain_id: "text", label: "文本能力", capability_ids: ["direct_answer"]},
          ],
        },
        domain_routing_interaction: {
          schema_version: "spatial-agent.domain-routing-interaction.v1",
          available: true,
          state: "candidate_selection",
          reason_code: "multiple_domains_matched",
          decision_id: "route-ambiguous",
          candidates: [
            {domain_id: "gis", label: "空间能力", capability_ids: ["boundary_lookup"]},
            {domain_id: "text", label: "文本能力", capability_ids: ["direct_answer"]},
          ],
          allowed_actions: ["select_domain"],
          actions: [{
            id: "select_domain",
            label: "选择领域",
            description: "fixture versioned routing action",
            input_schema: {type: "object", required: ["domain_id"], properties: {domain_id: {type: "string", title: "领域", enum: ["gis", "text"]}}, additionalProperties: false},
          }],
        },
      });
      if (String(body.request || "").includes("no match")) return json({
        status: "NEEDS_CLARIFICATION",
        domain_routing: {decision_id: "route-none", status: "NO_MATCH", reason_code: "no_domain_matched", candidates: []},
      });
      return json(queue("text", body.request, body.session_id), 202);
    }
    const selectMatch = target.pathname.match(/^\/domain-routing\/decisions\/([^/]+)\/select$/);
    if (selectMatch && method === "POST") return json({
      status: "SELECTED",
      decision_id: `route-override-${body.domain_id}`,
      selection: {domain_id: body.domain_id},
    });
    const match = target.pathname.match(/^\/domains\/([^/]+)(\/.*)?$/);
    if (!match) return json({detail: {code: "not_found", message: `mock route missing: ${url}`}}, 404);
    const domainId = decodeURIComponent(match[1]);
    const tail = match[2] || "";
    if (tail === "/capabilities") return json({domain_id: domainId, capabilities: [], actions: {actions: []}});
    if (tail === "/capabilities/runtime") return json({domain_id: domainId, status: "ready", runtime: {fixture: true}});
    if (tail === "/workflows") return json({domain_id: domainId, templates: {}});
    if (tail === "/actions") return json({domain_id: domainId, actions: []});
    if (tail === "/sessions" && method === "GET") { const sessionId = state.sessions[domainId] || `${domainId}-session`; return json({domain_id: domainId, sessions: [{session_id: sessionId, display_name: "对话1", domain_id: domainId}]}); }
    if (tail === "/sessions" && method === "POST") return json({session_id: `${domainId}-session`, display_name: "对话1", domain_id: domainId});
    if (/^\/sessions\/[^/]+\/runs$/.test(tail)) return json({domain_id: domainId, runs: []});
    if (tail === "/runs" && method === "GET") return json({domain_id: domainId, runs: []});
    if (tail === "/metrics") return json({domain_id: domainId, run_count: 0, total_tokens: 0, actions: {count: 0}});
    if (tail === "/action-executions") return json({domain_id: domainId, actions: []});
    if (tail === "/runs/async" && method === "POST") return json(queue(domainId, body.request, body.session_id), 202);
    const runMatch = tail.match(/^\/runs\/([^/]+)$/);
    if (runMatch && method === "GET") {
      const runId = decodeURIComponent(runMatch[1]);
      const item = state[runId] || {domainId, request: "restored", sessionId: `${domainId}-session`};
      return json(completed(item.domainId, runId, item.request, item.sessionId));
    }
    return json({detail: {code: "not_found", message: `mock route missing: ${url}`}}, 404);
  };
}

await command("Page.addScriptToEvaluateOnNewDocument", {source: `(${installDomainRoutingMock.toString()})();`});
const evaluate = async expression => {
  const result = await command("Runtime.evaluate", {expression, awaitPromise: true, returnByValue: true});
  if (result.result?.exceptionDetails) throw new Error(result.result.exceptionDetails.exception?.description || "浏览器脚本执行失败");
  return result.result?.result?.value;
};
const navigateReady = async () => {
  await command("Page.navigate", {url: consoleUrl});
  for (let attempt = 0; attempt < 120; attempt++) {
    if (await evaluate("Boolean(window.__consoleBootstrapReady && window.__consoleDomainReady)")) return;
    await sleep(100);
  }
  throw new Error("Console smart Domain bootstrap 未就绪");
};

await navigateReady();
const uniqueRaw = await evaluate(`(async()=>{
  const initial={options:[...$('domain').options].map(item=>({value:item.value,label:item.textContent})),requests:[...window.__domainRoutingSmoke.requests]};
  await sendChat('unique route');
  for(let i=0;i<100&&!window.__domainRoutingSmoke.requests.some(item=>item.url==='/domains/text/sessions?limit=50');i++) await new Promise(resolve=>setTimeout(resolve,20));
  const afterFirst={domain:$('domain').value,session:$('session').value,answer:$('answer').textContent,requests:[...window.__domainRoutingSmoke.requests]};
  await sendChat('bound follow up');
  return JSON.stringify({initial,afterFirst,afterSecond:[...window.__domainRoutingSmoke.requests]});
})()`);
const unique = JSON.parse(uniqueRaw || "{}");
if (unique.initial.options.map(item => item.value).join(",") !== "auto,gis,text") throw new Error(`智能选择没有位于动态领域之前：${JSON.stringify(unique.initial.options)}`);
if (unique.initial.requests.some(item => item.url.startsWith("/domains/"))) throw new Error(`未绑定 auto 模式预先访问了领域状态：${JSON.stringify(unique.initial.requests)}`);
const firstAuto = unique.afterFirst.requests.find(item => item.url === "/runs/auto" && item.method === "POST");
if (!firstAuto || firstAuto.body.async !== true || !String(firstAuto.body.session_id || "").startsWith("conversation-auto-") || "domain_id" in firstAuto.body) throw new Error(`首次 auto 请求必须使用异步和未预创建的中立会话 identity：${JSON.stringify(firstAuto)}`);
if (!unique.afterFirst.requests.some(item => item.url.startsWith("/domains/text/runs/text-run-"))) throw new Error("唯一匹配后没有按响应领域轮询");
if (unique.afterFirst.domain !== "auto" || unique.afterFirst.session !== firstAuto.body.session_id || !unique.afterFirst.answer.includes("text completed")) throw new Error(`自动运行没有保留 auto 模式并加载返回领域状态：${JSON.stringify(unique.afterFirst)}`);
const followUp = unique.afterSecond.filter(item => item.url === "/domains/text/runs/async" && item.method === "POST").at(-1);
if (!followUp || followUp.body.session_id !== firstAuto.body.session_id || followUp.body.domain_id !== "text") throw new Error(`后续 auto 请求没有沿已绑定会话领域：${JSON.stringify(followUp)}`);
if (unique.afterSecond.filter(item => item.url === "/runs/auto").length !== 1) throw new Error("已绑定后的请求不应再次自动选域");

await evaluate("localStorage.setItem('spatial-agent.domain-routing-smoke.preserve','1')");
await navigateReady();
const restoredRaw = await evaluate(`JSON.stringify({domain:$('domain').value,session:$('session').value,requests:window.__domainRoutingSmoke.requests})`);
const restored = JSON.parse(restoredRaw || "{}");
if (restored.domain !== "auto" || restored.session !== firstAuto.body.session_id || restored.requests.some(item => item.url === "/runs/auto") || !restored.requests.some(item => item.url.startsWith("/domains/text/sessions"))) throw new Error(`刷新后没有恢复自动选择的会话领域身份：${JSON.stringify(restored)}`);

await navigateReady();
const ambiguousRaw = await evaluate(`(async()=>{
  await sendChat('ambiguous route');
  const host=$('decisionEvidence').querySelector('[data-domain-routing-action-host]');
  const field=host?.querySelector('[data-action-field="domain_id"]');
  const before={answer:$('answer').textContent,interaction:$('decisionEvidence').textContent,options:[...(field?.options||[])].map(item=>item.value),schemaVersion:host?.dataset.schemaVersion||''};
  field.value='gis';
  host.querySelector('#domainActionExecute').click();
  for(let i=0;i<150&&!$('answer').textContent.includes('gis completed');i++) await new Promise(resolve=>setTimeout(resolve,20));
  return JSON.stringify({before,after:{domain:$('domain').value,session:$('session').value,answer:$('answer').textContent},requests:window.__domainRoutingSmoke.requests});
})()`);
const ambiguous = JSON.parse(ambiguousRaw || "{}");
if (ambiguous.before.options.join(",") !== ",gis,text" || ambiguous.before.schemaVersion !== "spatial-agent.domain-routing-interaction.v1" || !ambiguous.before.interaction.includes("boundary_lookup")) throw new Error(`歧义候选没有通过版本化 Action Host 进入通用交互区域：${JSON.stringify(ambiguous.before)}`);
const overrideRun = ambiguous.requests.find(item => item.url === "/runs/auto" && item.body.domain_routing_decision_id === "route-override-gis");
const overrideSelect = ambiguous.requests.find(item => item.url === "/domain-routing/decisions/route-ambiguous/select");
if (!overrideSelect || !overrideSelect.body.session_id || !overrideRun || overrideRun.body.session_id !== overrideSelect.body.session_id || overrideRun.body.async !== true || "domain_id" in overrideRun.body || !ambiguous.requests.some(item => item.url.startsWith("/domains/gis/runs/gis-run-")) || !ambiguous.after.answer.includes("gis completed")) throw new Error(`select_domain 没有携带会话化异步 override decision lineage 继续执行：${JSON.stringify(ambiguous.after)}`);

await navigateReady();
const noMatchRaw = await evaluate(`(async()=>{
  await sendChat('no match route');
  const host=$('decisionEvidence').querySelector('[data-domain-routing-action-host]');
  const field=host?.querySelector('[data-action-field="domain_id"]');
  return JSON.stringify({interaction:$('decisionEvidence').textContent,domains:[...(field?.options||[])].map(item=>item.value).filter(Boolean)});
})()`);
const noMatch = JSON.parse(noMatchRaw || "{}");
if (noMatch.domains.join(",") !== "gis,text" || !noMatch.interaction.includes("no_domain_matched")) throw new Error(`无匹配时没有展示可改选的动态领域：${JSON.stringify(noMatch)}`);

await navigateReady();
const manualRaw = await evaluate(`(async()=>{
  $('domain').value='gis';
  $('domain').dispatchEvent(new Event('change'));
  for(let i=0;i<120&&!window.__consoleDomainReady;i++) await new Promise(resolve=>setTimeout(resolve,20));
  await sendChat('manual gis route');
  return JSON.stringify({domain:$('domain').value,session:$('session').value,answer:$('answer').textContent,requests:window.__domainRoutingSmoke.requests});
})()`);
const manual = JSON.parse(manualRaw || "{}");
const manualSubmit = manual.requests.find(item => item.url === "/domains/gis/runs/async" && item.method === "POST");
if (manual.domain !== "gis" || !manualSubmit || manualSubmit.body.domain_id !== "gis" || !manualSubmit.body.session_id || manual.requests.some(item => item.url === "/runs/auto") || !manual.answer.includes("gis completed")) throw new Error(`手动领域行为发生回归：${JSON.stringify(manual)}`);

console.log(JSON.stringify({unique:{options:unique.initial.options,session:unique.afterFirst.session,answer:unique.afterFirst.answer},restored:{domain:restored.domain,session:restored.session},ambiguous:ambiguous.before,noMatch,manual:{domain:manual.domain,session:manual.session,answer:manual.answer}}));
socket.close();
process.exit(0);
