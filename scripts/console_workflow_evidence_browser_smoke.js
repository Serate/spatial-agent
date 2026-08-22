/* M195 browser smoke: the dynamic Console renders a composed workflow. */
;(async () => {
  const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
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
    if (resolve) { pending.delete(message.id); resolve(message); }
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

  for (let attempt = 0; attempt < 240; attempt++) {
    const ready = await command("Runtime.evaluate", {
      expression: "window.__consoleBootstrapReady === true && typeof renderWorkflowEvidence === 'function' && !!window.ConsoleWorkflowEvidence",
      returnByValue: true,
    });
    if (ready.result?.result?.value) break;
    await sleep(250);
    if (attempt === 239) throw new Error("Console workflow renderer was not ready");
  }

  const result = await command("Runtime.evaluate", {
    expression: `(() => {
      renderWorkflowEvidence({
        status: 'COMPLETED',
        plan: {steps: [
          {id: 'boundary--filter', depends_on: []},
          {id: 'dem--metadata', depends_on: ['boundary--filter']},
        ]},
        plan_evidence: {workflow_selection: {
          state: 'selected',
          workflow_components: [
            {component_id: 'boundary', template_id: 'admin_boundary_query', evidence_keys: ['geometry']},
            {component_id: 'dem', template_id: 'raster_metadata', depends_on_components: ['boundary'], evidence_keys: ['metadata']},
          ],
        }},
      });
      return {
        visible: document.querySelector('.workflow-evidence-result')?.classList.contains('is-visible') === true,
        cards: document.querySelectorAll('.workflow-component-card').length,
        dependencyText: document.querySelector('.workflow-component-card[data-component-id="dem"]')?.textContent || '',
      };
    })()`,
    returnByValue: true,
  });
  if (result.result.exceptionDetails) throw new Error(JSON.stringify(result.result.exceptionDetails));
  const snapshot = result.result.result.value;
  console.log(JSON.stringify(snapshot));
  if (!snapshot.visible || snapshot.cards !== 2 || !snapshot.dependencyText.includes('boundary')) {
    throw new Error(`workflow evidence panel did not render correctly: ${JSON.stringify(snapshot)}`);
  }
  socket.close();
  process.exit(0);
})().catch(error => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
