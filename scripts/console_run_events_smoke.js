"use strict";

// Compact, transport-only smoke for the browser event consumer.  It does not
// start the application or call a model; browser/Docker acceptance owns that.
const fs = require("fs");
const assert = require("assert");

const source = fs.readFileSync("web/src/console_run_events.js", "utf8");
const browserWindow = { setTimeout, clearTimeout, setInterval, clearInterval };
new Function("window", source)(browserWindow);
const api = browserWindow.ConsoleRunEvents;
assert(api && typeof api.create === "function");

async function main() {
  const sseEvents = [];
  let sseListener = null;
  const event = (sequence, kind, status, data = {}, terminal = false) => ({
    schema_version: "spatial-agent.run-event.v1",
    run_id: "run-sse",
    sequence,
    kind,
    phase: kind === "answer_delta" ? "answer" : "plan",
    status,
    message: "状态更新",
    data,
    terminal,
  });
  const sseSource = {
    addEventListener(name, listener) { if (name === "run_event") sseListener = listener; },
    close() {},
  };
  const sseConsumer = api.create({
    runId: "run-sse",
    eventsPath: sequence => "/runs/run-sse/events?cursor=" + sequence,
    eventSourceFactory: () => sseSource,
    onEvent: event => sseEvents.push(event.sequence),
  });
  sseConsumer.start();
  sseListener({ data: JSON.stringify(event(1, "stage_started", "PLANNING")) });
  sseListener({ data: JSON.stringify(event(1, "stage_started", "PLANNING")) });
  sseListener({ data: JSON.stringify(event(2, "answer_delta", "RUNNING", { answer_delta: "a".repeat(700) })) });
  assert.strictEqual(sseEvents.length, 2);
  assert.strictEqual(api.normalize(event(2, "answer_delta", "RUNNING", { answer_delta: "a".repeat(700) })).data.answer_delta.length, 512);
  assert.strictEqual(api.normalize({ ...event(3, "stage_progress", "PLANNING"), schema_version: "wrong" }), null);
  sseListener({ data: JSON.stringify(event(3, "run_completed", "COMPLETED", {}, true)) });
  assert.deepStrictEqual(sseEvents, [1, 2, 3]);

  let pollCount = 0;
  const pollingEvents = [];
  browserWindow.fetch = async () => ({
    ok: true,
    status: 200,
    async json() {
      pollCount += 1;
      const sequence = pollCount === 1 ? 3 : 4;
      return { events: [{ schema_version: "spatial-agent.run-event.v1", run_id: "run-poll", sequence, kind: sequence === 4 ? "run_completed" : "stage_progress", phase: sequence === 4 ? "evidence" : "execute", status: sequence === 4 ? "COMPLETED" : "EXECUTING", message: "状态更新", data: {}, terminal: sequence === 4 }] };
    },
  });
  const polling = [];
  const pollConsumer = api.create({
    runId: "run-poll",
    eventsPath: "/runs/run-poll/events",
    eventSourceFactory: null,
    fetchImpl: browserWindow.fetch,
    pollInterval: 5,
    onEvent: event => polling.push(event.sequence),
  });
  pollConsumer.start();
  await new Promise(resolve => setTimeout(resolve, 420));
  assert.deepStrictEqual(polling, [3, 4]);
  assert.strictEqual(pollConsumer.lastSequence, 4);

  let failedPolls = 0;
  const failedConsumer = api.create({
    runId: "run-fail",
    eventsPath: "/runs/run-fail/events",
    eventSourceFactory: null,
    fetchImpl: async () => { failedPolls += 1; return { ok: false, status: 500, json: async () => ({}) }; },
    pollInterval: 5,
  });
  failedConsumer.start();
  // The consumer intentionally clamps its polling interval to 50ms and uses
  // bounded exponential backoff, so allow enough time for three attempts.
  await new Promise(resolve => setTimeout(resolve, 420));
  assert.strictEqual(failedPolls, 3);
  console.log("console run events smoke: ok");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
