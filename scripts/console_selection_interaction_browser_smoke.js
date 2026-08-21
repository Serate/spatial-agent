/*
 * M169 browser acceptance: preview -> confirmation -> execution.
 *
 * This uses the real Docker HTTP service and the real Console renderer.  It
 * proves that the preview fingerprint is carried into the submitted request,
 * that the server keeps the same plan identity, and that the confirmation
 * action reaches a completed result.  It intentionally uses the rule planner
 * and memory backend so the browser gate remains deterministic and offline.
 * Requires Chrome started with scripts/console_cdp_start.ps1.
 */
;(async () => {
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const consoleUrl = process.env.CONSOLE_URL || "http://127.0.0.1:8088/";
const cdpUrl = process.env.CDP_URL || "http://127.0.0.1:9222";
const pages = await (await fetch(`${cdpUrl}/json/list`)).json();
const page = pages.find(item => item.type === "page");
if (!page) throw new Error("Chrome CDP page was not found");

const socket = new WebSocket(page.webSocketDebuggerUrl);
process.on("exit", () => { try { socket.close(); } catch {} });
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

for (let attempt = 0; attempt < 80; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "typeof $ === 'function' && typeof previewPlan === 'function' && typeof sendChat === 'function' && typeof renderRun === 'function' && !!$('requireConfirmation')",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 79) throw new Error("Console 页面脚本未就绪");
}

const result = await command("Runtime.evaluate", {
  expression: `(async()=>{
    const sessionId='m169-preview-browser-'+Date.now();
    const sessionOption=document.createElement('option');
    sessionOption.value=sessionId;
    sessionOption.textContent='M169预览验收';
    $('session').append(sessionOption);
    $('session').value=sessionId;
    $('planner').value='rule';
    $('backend').value='memory';
    $('workflow').value='';
    $('workflow').dispatchEvent(new Event('change',{bubbles:true}));
    $('requireConfirmation').checked=true;
    $('prompt').value='查询DEM栅格元数据';

    await previewPlan();
    const previewFingerprint=lastPlanPreview?.fingerprint||'';
    if(!previewFingerprint) throw new Error('计划预览没有返回 plan fingerprint');

    await sendChat('查询DEM栅格元数据');
    const plannedRun=lastRunData||{};
    const initialState=document.querySelector('[data-selection-state]')?.getAttribute('data-selection-state')||'';
    const submittedFingerprint=(plannedRun.plan_identity||plannedRun.plan_evidence?.plan_identity||{}).fingerprint||'';
    const selectedCapability=plannedRun.result?.selection_interaction?.selection?.selected_capability_id||'';
    const confirm=document.querySelector('[data-selection-action="confirm"]');
    if(!confirm) throw new Error('确认动作未渲染');
    if(initialState!=='confirmation_required') throw new Error('请求未进入 confirmation_required');
    if(submittedFingerprint!==previewFingerprint) {
      throw new Error('预览与提交计划不一致: preview=' + previewFingerprint + ' submitted=' + submittedFingerprint);
    }

    confirm.click();
    let finalState='';
    let finalStatus='';
    for(let attempt=0;attempt<100;attempt++){
      finalState=document.querySelector('[data-selection-state]')?.getAttribute('data-selection-state')||'';
      finalStatus=$('status')?.textContent||'';
      if(finalState==='completed') break;
      await sleep(250);
    }
    const completedRun=lastRunData||{};
    const finalFingerprint=(completedRun.plan_identity||completedRun.plan_evidence?.plan_identity||{}).fingerprint||'';
    return JSON.stringify({
      sessionId,
      previewFingerprint,
      submittedFingerprint,
      finalFingerprint,
      selectedCapability,
      initialState,
      finalState,
      finalStatus,
      status:completedRun.status||'',
      artifact:Boolean(completedRun.artifact_ref),
      moduleLoaded:Boolean(window.ConsoleSelectionInteraction),
    });
  })()`,
  awaitPromise: true,
  returnByValue: true,
});
if (result.result.exceptionDetails) {
  throw new Error(JSON.stringify(result.result.exceptionDetails));
}
const snapshot = JSON.parse(result.result.result.value);
console.log(JSON.stringify(snapshot));
if (snapshot.initialState !== "confirmation_required" || snapshot.finalState !== "completed") {
  throw new Error(`preview confirmation flow did not complete: ${JSON.stringify(snapshot)}`);
}
if (!snapshot.previewFingerprint || snapshot.previewFingerprint !== snapshot.submittedFingerprint || snapshot.submittedFingerprint !== snapshot.finalFingerprint) {
  throw new Error(`plan fingerprint drifted across preview/submit/complete: ${JSON.stringify(snapshot)}`);
}
if (!snapshot.selectedCapability || !snapshot.artifact || !snapshot.moduleLoaded) {
  throw new Error(`final result evidence is incomplete: ${JSON.stringify(snapshot)}`);
}
socket.close();
process.exit(0);
})().catch(error => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
