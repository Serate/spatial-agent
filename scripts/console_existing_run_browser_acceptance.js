/* Explicit browser acceptance for rendering one persisted run without re-execution. */

;(async () => {
  const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
  const consoleUrl = process.env.CONSOLE_URL || "http://127.0.0.1:8088/";
  const cdpUrl = process.env.CDP_URL || "http://127.0.0.1:9222";
  const runId = String(process.argv[2] || process.env.RUN_ID || "").trim();
  const domainId = String(process.argv[3] || process.env.DOMAIN_ID || "gis").trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$/.test(runId)) {
    throw new Error("RUN_ID is required and must be a safe identifier");
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(domainId)) {
    throw new Error("DOMAIN_ID must be a safe identifier");
  }

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
  await command("Runtime.enable");
  await command("Page.navigate", {url: consoleUrl});
  for (let attempt = 0; attempt < 120; attempt++) {
    const ready = await command("Runtime.evaluate", {
      expression: "window.__consoleBootstrapReady === true && typeof openRunDetail === 'function'",
      returnByValue: true,
    });
    if (ready.result?.result?.value) break;
    await sleep(250);
    if (attempt === 119) throw new Error("Console run renderer was not ready");
  }

  const opened = await command("Runtime.evaluate", {
    expression: `(async () => {
      document.querySelector('#planner').value = 'openai';
      document.querySelector('#backend').value = 'local';
      await openRunDetail(${JSON.stringify(runId)}, ${JSON.stringify(domainId)});
      return true;
    })()`,
    awaitPromise: true,
    returnByValue: true,
  });
  if (opened.result?.exceptionDetails) {
    throw new Error(opened.result.exceptionDetails.exception?.description || "run detail failed");
  }

  let snapshot = null;
  for (let attempt = 0; attempt < 80; attempt++) {
    const observed = await command("Runtime.evaluate", {
      expression: `(() => {
        const envelope = lastRunData?.result || {};
        const panels = envelope.views?.panels || {};
        return {
          loaded: lastRunData?.run_id === ${JSON.stringify(runId)},
          status: lastRunData?.status || null,
          resultType: lastRunData?.result_type || envelope.type || null,
          declaredPanels: (envelope.workspace?.panels || []).slice(0, 12),
          viewKinds: Object.fromEntries(Object.entries(panels).slice(0, 12).map(([id, value]) => [id, value?.kind || null])),
          genericVisible: document.querySelector('.generic-result')?.classList.contains('is-visible') === true,
          mapVisible: document.querySelector('.map-result')?.classList.contains('is-visible') === true,
          mapPaths: document.querySelectorAll('#map .leaflet-overlay-pane path, #map svg path').length,
          mapEmpty: Boolean(document.querySelector('#map .map-empty')),
          answerStream: typeof window.ConsoleAnswerStream?.create === 'function',
          traceItems: document.querySelectorAll('#trace li').length,
          workflowCards: document.querySelectorAll('.workflow-component-card').length,
          errorVisible: Boolean(document.querySelector('#error .error')),
        };
      })()`,
      returnByValue: true,
    });
    snapshot = observed.result?.result?.value || null;
    if (snapshot?.loaded && snapshot?.genericVisible && snapshot?.mapVisible) break;
    await sleep(250);
  }
  socket.close();
  console.log(JSON.stringify(snapshot));
  if (
    !snapshot?.loaded
    || snapshot.status !== "COMPLETED"
    || typeof snapshot.resultType !== "string"
    || !snapshot.resultType
    || !snapshot.declaredPanels.includes("map")
    || !snapshot.viewKinds.map
    || !snapshot.answerStream
    || !snapshot.genericVisible
    || !snapshot.mapVisible
    || snapshot.mapEmpty
    || snapshot.traceItems < 1
    || snapshot.errorVisible
  ) {
    throw new Error(`persisted run did not render dynamically: ${JSON.stringify(snapshot)}`);
  }
})().catch(error => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
