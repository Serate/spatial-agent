/*
 * M167 browser smoke: render a domain-neutral candidate card in the real
 * Console page and verify that its action submits capability_id.
 *
 * The response is intentionally stubbed inside the page. Backend selection
 * and continuation are covered by the Docker Python contract tests; this
 * smoke isolates the browser renderer/action seam without another run.
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
  }, 20000);
});
await new Promise(resolve => { socket.onopen = resolve; });
await command("Page.enable");
await command("Network.enable");
await command("Network.setCacheDisabled", {cacheDisabled: true});
await command("Runtime.enable");
await command("Page.addScriptToEvaluateOnNewDocument", {source: `
  window.__m167Captured = null;
  const __m167OriginalFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    if (String(input).includes('/interaction') && init?.method === 'POST') {
      window.__m167Captured = {url: String(input), body: JSON.parse(init.body || '{}')};
      return new Response(JSON.stringify({
        run_id: 'm167-browser-candidate',
        status: 'COMPLETED',
        answer: '已完成能力选择',
        result: {selection_interaction: {
          schema_version: 'spatial-agent.selection-interaction.v1',
          available: true,
          state: 'completed',
          reason_code: 'run_completed',
          status: 'COMPLETED',
          allowed_actions: [],
          selection: {state: 'selected', candidate_ids: ['text_summary'], candidate_details: []},
          missing_fields: [],
        }},
      }), {status: 200, headers: {'Content-Type': 'application/json'}});
    }
    return __m167OriginalFetch(input, init);
  };
`});
await command("Page.navigate", {url: consoleUrl});

for (let attempt = 0; attempt < 60; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "typeof $ === 'function' && typeof renderSelectionInteraction === 'function'",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 59) throw new Error("Console 页面脚本未就绪");
}

const result = await command("Runtime.evaluate", {
  expression: `(async()=>{
    const candidate={
      id:'text_summary',
      label:'文本摘要',
      description:'将输入内容压缩为可读摘要。',
      available:true,
      input_facts:[{id:'source',label:'输入来源',kind:'entity'}],
      result_types:['text_summary_result'],
      actions:['select_capability'],
      workflow:null,
    };
    const data={
      run_id:'m167-browser-candidate',
      status:'NEEDS_CLARIFICATION',
      result:{
        selection_interaction:{
          schema_version:'spatial-agent.selection-interaction.v1',
          available:true,
          state:'candidate_selection',
          reason_code:'selection_requires_user_choice',
          status:'NEEDS_CLARIFICATION',
          allowed_actions:['select_capability','cancel'],
          selection:{
            state:'ambiguous',
            candidate_ids:['text_summary'],
            candidate_workflow_ids:[],
            candidate_details:[candidate],
          },
          blocked_actions:['repair'],
          action_preconditions:{
            schema_version:'spatial-agent.action-precondition.v1',
            available:true,
            state:'blocked',
            action_allowed:false,
            enforcement:'enforced',
            reason_code:'action_preconditions_blocked',
            condition_count:1,
            conditions:[{id:'alignment',status:'blocked',blocking:true}],
          },
          action_receipt:{
            schema_version:'spatial-agent.action-receipt.v1',
            action_id:'repair',
            status:'FAILED',
            reused:true,
          },
          repair_lineage:[{phase:'planning',repair_status:'repaired',repair_reason_code:'replacement_selected'}],
          evidence_action_guidance:{
            schema_version:'spatial-agent.evidence-action-guidance.v1',
            available:true,
            state:'degraded',
            reason_code:'selection_requires_facts',
            recommended_actions:['provide_facts'],
            missing_fields:[{id:'region',label:'区域',kind:'entity'}],
            source:'domain',
          },
          missing_fields:[],
        },
      },
    };
    lastRunData=data;
    renderRun=()=>{};
    const panel=$('decisionEvidence');
    panel.innerHTML=renderSelectionInteraction(data);
    panel.querySelectorAll('[data-selection-action]').forEach(button=>button.addEventListener('click',()=>selectionInteractionAction(button.dataset.selectionAction,button.dataset.runId,button.dataset.selectionValue)));
    const card=panel.querySelector('.selection-candidate');
    const button=panel.querySelector('[data-selection-action="select_capability"]');
    if(!card||!button) throw new Error('候选卡片或选择按钮未渲染');
    button.click();
    for(let attempt=0;attempt<40&&!window.__m167Captured;attempt++) await new Promise(resolve=>setTimeout(resolve,50));
    return JSON.stringify({
      cardText:card.textContent||'',
      guidanceText:panel.textContent||'',
      capabilityId:window.__m167Captured?.body?.capability_id||'',
      action:window.__m167Captured?.body?.action||'',
      editorOpen:Boolean($('workflowEditor')?.open),
    });
  })()`,
  awaitPromise: true,
  returnByValue: true,
});
if (result.result.exceptionDetails) throw new Error(JSON.stringify(result.result.exceptionDetails));
const snapshot = JSON.parse(result.result.result.value);
console.log(JSON.stringify(snapshot));
if (!snapshot.cardText.includes("文本摘要")) throw new Error("候选卡片未显示领域标签");
if (!snapshot.guidanceText.includes("系统建议") || !snapshot.guidanceText.includes("补充事实")) throw new Error("指导动作未通过通用 renderer 展示");
if (!snapshot.guidanceText.includes("动作凭据") || !snapshot.guidanceText.includes("修复链") || !snapshot.guidanceText.includes("已阻断")) throw new Error("interaction receipt/precondition/lineage 未通过通用 renderer 展示");
if (snapshot.action !== "select_capability" || snapshot.capabilityId !== "text_summary") {
  throw new Error(`capability_id action was not submitted: ${JSON.stringify(snapshot)}`);
}
if (snapshot.editorOpen) throw new Error("候选能力选择不应强制打开 GIS workflow editor");
socket.close();
process.exit(0);
