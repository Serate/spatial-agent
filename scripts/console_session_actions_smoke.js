/*
 * Session actions smoke: a fresh Console must allow a new conversation before
 * auto-domain binding, and must expose a deterministic clear-all action.
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
  }, 10000);
});
await new Promise(resolve => { socket.onopen = resolve; });
await command("Page.enable");
await command("Runtime.enable");
await command("Page.navigate", {url: consoleUrl});
for (let attempt = 0; attempt < 80; attempt++) {
  const ready = await command("Runtime.evaluate", {
    expression: "typeof $ === 'function' && typeof newSession === 'function' && Boolean(window.__consoleBootstrapReady)",
    returnByValue: true,
  });
  if (ready.result?.result?.value) break;
  await sleep(250);
  if (attempt === 79) throw new Error("Console 页面脚本未就绪");
}
const result = await command("Runtime.evaluate", {
  expression: `(async()=>{
    window.localStorage.removeItem('spatial-agent.console.auto-binding');
    autoDomainBinding=null;
    autoDraftSessionId='';
    localDraftSessionIds.clear();
    sessionDomains.clear();
    $('session').innerHTML='';
    $('domain').value='auto';
    $('domain').dispatchEvent(new Event('change',{bubbles:true}));
    await new Promise(resolve=>setTimeout(resolve,100));
    if($('newSession').disabled) throw new Error('自动领域未绑定时新建对话按钮被禁用');
    if($('clearAllSessions').disabled) throw new Error('清空全部对话按钮不可用');
    const heroRect=document.querySelector('.hero').getBoundingClientRect();
    const chatRect=$('chatPanel').getBoundingClientRect();
    const decisionRect=$('decisionMode').getBoundingClientRect();
    if(heroRect.height>130) throw new Error('准备好执行任务区域仍然过高：'+Math.round(heroRect.height)+'px');
    if(chatRect.height<600) throw new Error('右侧对话工作区仍然过短：'+Math.round(chatRect.height)+'px');
    if(decisionRect.top>heroRect.top+55) throw new Error('决策状态没有与标题并排');
    const before=$('session').value;
    const beforeCount=$('session').options.length;
    const created=await newSession();
    const after=$('session').value;
    const afterCount=$('session').options.length;
    if(!created?.session_id || !after || after===before || afterCount<=beforeCount) throw new Error('新建对话没有切换到新会话');
    if(typeof clearAllSessions!=='function') throw new Error('缺少清空全部对话入口');
    const cleared=await clearAllSessions({confirm:false,includePersisted:false,includeRouting:false});
    if(cleared.remaining!==1 || $('session').options.length!==1) throw new Error('清空全部对话后没有保留一个新的空白会话');
    if($('messages').querySelectorAll('.msg').length!==2) throw new Error('清空全部对话后消息区未重置');
    return JSON.stringify({before,beforeCount,created:created.session_id,after,afterCount,heroHeight:Math.round(heroRect.height),chatHeight:Math.round(chatRect.height),decisionTop:Math.round(decisionRect.top-heroRect.top),cleared});
  })()`,
  awaitPromise: true,
  returnByValue: true,
});
if (result.result.exceptionDetails) throw new Error(result.result.exceptionDetails.exception?.description || "session action failed");
console.log(result.result.result.value);
socket.close();
