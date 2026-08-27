# Spec：M313 实时 Agent 交互与可观测执行体验

## Objective

面向复杂、多步骤 Agent 请求，用户无需等待所有工具执行结束即可看到真实的生命周期
进展、当前动作、耗时和阶段摘要；任务完成后，最终答案可以增量显示，并与结构化
结果、地图、证据和 artifact 保持一致。

用户看到的是简洁的实时工作状态，而不是模型隐藏思维链。详细过程默认收起，必要时
展开查看结构化计划摘要、工具结果状态和证据来源。

## Assumptions

1. M312 已完成 Result/View/Evidence、异步生命周期、SQLite/artifact 恢复和现有原生
   Console；本阶段不重写这些公共边界。
2. 当前项目使用 Python 标准库、FastAPI、SQLite、Node smoke 和原生 JavaScript；不
   引入新的前端框架或消息中间件。
3. 事件需要服务端持久化，才能支持 SSE 断线续传和服务重启后的读取；内存模式仍需
   提供等价的有界实现。
4. 真实模型可能不支持 token 流或中转不稳定，因此必须保留完整答案 fallback 和
   polling fallback。
5. 真实模型、真实 GIS 和 Docker 只在阶段收口显式验收，默认测试保持离线、精简。

## Tech Stack

- Python 现有 Runtime、Application、FastAPI、SQLite/artifact。
- 原生 SSE（`text/event-stream`）和现有 HTTP transport seam。
- 原生 JavaScript/CSS Console；现有 Leaflet 和 Result projection 不变。
- Python `unittest`、Node projection/browser smoke、Docker 生产镜像。

## Commands

```text
Static:
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python -m compileall -q agent domains tests scripts

Architecture:
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python scripts/architecture_check.py --strict

Contract (stage close):
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python -m unittest tests.test_m313_realtime_events -v

Frontend projection:
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent node scripts/console_result_projection_smoke.js

Readiness:
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build spatial-agent
```

真实模型只在离线契约、Docker readiness 和真实数据路径通过后显式调用一次，并只保存
脱敏 receipt。

## Project Structure

- `agent/run_events.py`：公共 RunEvent schema、阶段枚举、脱敏归一化和 cursor 语义。
- `agent/runtime_state.py`、`agent/sqlite_store.py`：内存/SQLite 事件账本适配。
- `agent/runtime_core/run_lifecycle.py`、`agent/runtime.py`：真实阶段事件发射 seam。
- `agent/application/http.py`、`production_api.py`、`serve_api.py`：共享语义读取和 SSE
  传输适配。
- `web/src/console_app.js`、`web/src/index.html`、`web/src/styles.css`：实时事件、
  阶段反馈、摘要和答案增量展示。
- `tests/test_m313_realtime_events.py`：合并后的事件契约、游标、恢复和生命周期契约。
- `docs/`、`tasks/`：Spec、Plan、中文问题日志和恢复交接账本。

## Code Style

事件生产者只提交领域中立的稳定字段，读取方负责展示：

```python
event = event_sink(
    run_id=result.run_id,
    phase="plan",
    kind="stage_started",
    status=result.status.value,
    message="正在生成任务计划",
    data={"stage_index": 3, "stage_count": 7},
)
```

`message` 和 `data` 必须经过统一脱敏、长度和字段 allowlist；工具名称可以作为安全
的当前动作标识，但不得把原始参数、文件路径或错误原文写入事件。

## RunEvent Contract

事件至少包含：

- `schema_version: spatial-agent.run-event.v1`
- `event_id`：稳定唯一 ID
- `sequence`：同一 `run_id` 内单调递增游标
- `run_id`、`created_at`
- `kind`：`stage_started`、`stage_progress`、`tool_started`、`tool_completed`、
  `answer_delta`、`heartbeat`、`run_completed`、`run_failed` 等
- `phase`：`resolve`、`clarify`、`plan`、`validate`、`execute`、`answer`、`evidence`
- `status`、`message`、可选安全 `data`

同一事件序列通过 `GET /runs/{run_id}/events` 读取；SSE 使用相同 projection，查询
参数包含 `after`，请求头 `Last-Event-ID` 优先作为游标。终态事件必须可重复读取，
并且服务重启后序号和内容保持不变。

## Testing Strategy

- 事件契约：覆盖字段归一化、脱敏、序号、非法游标和有界容量。
- 事件账本：覆盖内存、SQLite 追加读取、重启读取和同一 run 的顺序一致性。
- 生命周期：覆盖至少一个完整 run 的阶段事件、工具开始/完成、失败和终态事件。
- HTTP：覆盖 SSE content type、`Last-Event-ID`、断线续传和空游标；同时保留 polling。
- 前端：只增加一个实时事件消费/状态展示 smoke，不重复既有全量浏览器套件。
- Live：Docker + 真实 GIS/真实模型最多一次，验证事件终态和最终 Result identity。

## Boundaries

- Always：复用 Runtime 生命周期和统一 Result/Evidence；事件必须可恢复、可排序、可脱敏。
- Ask first：新增外部消息队列、第三方前端框架、改变公共 schema 兼容策略或改变默认
  部署入口。
- Never：展示原始隐藏思维链、Prompt、密钥、模型原文、完整异常堆栈或私有路径；不以
  前端动画伪造后端进度；不绕过现有计划校验和执行授权。

## Success Criteria

1. 一个复杂异步请求能够产生多个真实阶段事件，并在内存和 SQLite 中按序读取。
2. SSE 能从指定游标续传，服务重启后仍能读取同一 run 的历史事件；读取失败时 polling
   仍可完成任务展示。
3. 前端在等待期间显示当前阶段、当前动作、耗时、心跳和错误/恢复状态，不再只显示静止
   loading；阶段摘要默认收起。
4. 结构化计划和工具参数经过校验后才展示；答案只在事实可用后生成，并能以 token/delta
   事件逐步呈现，provider 不支持流式时完整答案 fallback 正常工作。
5. CLI、HTTP、前端和重启恢复消费相同事件与结果契约，核心 Result、Evidence 和 artifact
   identity 不变。
6. Docker 精简门禁、一次浏览器实时 smoke、真实 GIS/模型显式验收和交接文档完成；不把
   实时功能的默认验证依赖外部网络。

## Open Questions

- SSE 的实现先放在 FastAPI 入口和共享 HTTP 语义读取 seam；stdlib `serve_api.py` 是否
  需要完整长连接适配，在 transport acceptance 前依据部署使用情况决定。
- 真实模型答案 token 流以当前 OpenAI-compatible client 的能力为准；不可用时不阻塞阶段
  事件流和完整答案 fallback。
