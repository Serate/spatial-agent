"use strict";

// Regression smoke for the user-visible answer cadence.  The provider may
// deliver a whole text chunk at once; the Console must reveal it one character
// per render tick and drain it before the terminal result replaces the shell.
const fs = require("fs");
const assert = require("assert");

const html = fs.readFileSync("web/src/index.html", "utf8");
const appScript = html.indexOf("console_app.js");
assert(appScript >= 0, "console app must be present");
const streamScript = html.indexOf("console_answer_stream.js");
assert(streamScript >= 0 && streamScript < appScript, "answer stream must load before console app");
const source = fs.readFileSync("web/src/console_answer_stream.js", "utf8");
const appSource = fs.readFileSync("web/src/console_app.js", "utf8");
const stylesSource = fs.readFileSync("web/src/styles.css", "utf8");
const browserWindow = { setTimeout, clearTimeout };
new Function("window", source)(browserWindow);
const api = browserWindow.ConsoleAnswerStream;
assert(api && typeof api.create === "function", "answer stream API is unavailable");
assert(appSource.includes("createLiveAssistantMessage"), "live chat placeholder must be wired");
assert(appSource.includes("renderLiveAssistantMessage"), "live chat message must be updated");
assert(stylesSource.includes("live-answer-dots"), "live chat dots animation must be styled");

function extractFunction(source, name) {
  const start = source.indexOf(`function ${name}`);
  assert(start >= 0, `${name} must be present`);
  const opening = source.indexOf("{", start);
  let depth = 0;
  for (let index = opening; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(start, index + 1);
  }
  throw new Error(`${name} is not balanced`);
}

function fakeElement(tagName) {
  const element = {
    tagName,
    className: "",
    textContent: "",
    title: "",
    dataset: {},
    children: [],
    parentNode: null,
    scrollTop: 0,
    scrollHeight: 0,
    attributes: {},
    append(...items) {
      items.forEach(item => { item.parentNode = element; element.children.push(item); });
    },
    appendChild(item) {
      element.append(item);
      return item;
    },
    remove() {
      if (!element.parentNode) return;
      element.parentNode.children = element.parentNode.children.filter(item => item !== element);
      element.parentNode = null;
    },
    setAttribute(name, value) { element.attributes[name] = String(value); },
    removeAttribute(name) { delete element.attributes[name]; },
    addEventListener() {},
    classList: {
      add(...names) { element.className = `${element.className} ${names.join(" ")}`.trim(); },
      remove(...names) { element.className = element.className.split(/\s+/).filter(name => !names.includes(name)).join(" "); },
    },
  };
  return element;
}

const messages = fakeElement("div");
const fakeDocument = {createElement: fakeElement};
const createLiveAssistantMessage = new Function(
  "document", "$", `return (${extractFunction(appSource, "createLiveAssistantMessage")});`
)(fakeDocument, id => id === "messages" ? messages : null);
const renderLiveAssistantMessage = new Function(
  "liveRunState", "$", `return (${extractFunction(appSource, "renderLiveAssistantMessage")});`
);
const liveMessage = createLiveAssistantMessage("run-chat");
assert.strictEqual(messages.children.length, 1, "live answer placeholder must be added to chat");
assert.strictEqual(liveMessage.bubble.attributes["aria-label"], "智能体正在生成答案");
const chatState = {runId: "run-chat", answerMessage: liveMessage};
renderLiveAssistantMessage(chatState, id => id === "messages" ? messages : null)("第一段");
assert.strictEqual(liveMessage.typing, null, "typing placeholder must be removed on first answer text");
assert.strictEqual(liveMessage.bubble.textContent, "第一段", "chat bubble must receive streamed answer text");

const answerElement = { textContent: "", className: "" };
const subtitleElement = { textContent: "" };
const handlerScheduled = [];
const handlerRendered = [];
const answerStream = api.create({
  onText: text => {
    handlerRendered.push(text);
    answerElement.textContent = text;
  },
  schedule: callback => { handlerScheduled.push(callback); return handlerScheduled.length; },
  cancelSchedule: () => {},
});
const liveRunState = { runId: "run-answer", finalizing: false, answerBuffer: "", answerStream, lastSequence: 0, lastEventAt: 0, eventCount: 0, currentPhase: "" };
const answerHandler = new Function(
  "liveRunState", "$", "setStatus", "appendLiveEvent", "refreshLiveSummary", "window",
  `return (${extractFunction(appSource, "handleLiveEvent")});`
)(
  liveRunState,
  id => id === "answer" ? answerElement : subtitleElement,
  () => {},
  () => {},
  () => {},
  { ConsoleRunEvents: { phaseLabel: () => "答案" } },
);
answerHandler({
  run_id: "run-answer",
  sequence: 1,
  phase: "answer",
  kind: "answer_delta",
  status: "RUNNING",
  message: "正在生成答案",
  data: { answer_delta: "分析结果" },
});
assert.deepStrictEqual(handlerRendered, [], "a whole provider chunk must not render synchronously");
handlerScheduled.shift()();
assert.strictEqual(answerElement.textContent, "分", "the live handler must reveal only the first character on the first render tick");

async function main() {
  const scheduled = [];
  const rendered = [];
  const stream = api.create({
    onText: text => rendered.push(text),
    schedule: callback => { scheduled.push(callback); return scheduled.length; },
    cancelSchedule: () => {},
  });

  stream.push("分析结果");
  assert.deepStrictEqual(rendered, [], "a provider chunk must not render synchronously");
  assert.strictEqual(scheduled.length, 1, "one render tick should be scheduled");

  scheduled.shift()();
  assert.deepStrictEqual(rendered, ["分"], "the first render tick must reveal one character");
  scheduled.shift()();
  assert.deepStrictEqual(rendered, ["分", "分析"], "each render tick must reveal at most one character");

  const drained = stream.finish("分析结果");
  assert.strictEqual(typeof drained?.then, "function", "finish must be awaitable");
  while (scheduled.length) scheduled.shift()();
  await drained;
  assert.strictEqual(rendered.at(-1), "分析结果", "terminal finish must leave the complete answer visible");
  assert(rendered.length >= 4, "answer should visibly progress before completion");

  const correctionScheduled = [];
  const correctionRendered = [];
  const correction = api.create({
    onText: text => correctionRendered.push(text),
    schedule: callback => { correctionScheduled.push(callback); return correctionScheduled.length; },
    cancelSchedule: () => {},
  });
  correction.push("旧答案");
  correctionScheduled.shift()();
  const correctionDrain = correction.finish("新答案");
  while (correctionScheduled.length) correctionScheduled.shift()();
  await correctionDrain;
  assert.strictEqual(correctionRendered.at(-1), "新答案", "terminal result must correct a divergent streamed prefix");
  console.log("console answer stream smoke: ok");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
