# Spec: M278 Composite 可恢复生命周期

## Objective

让 M275/M276/M277 的 Composite 请求从“同步 HTTP 能执行”推进到与普通 Agent Run 一致的可恢复生命周期：支持同步结果持久化、异步提交与轮询、幂等、SQLite 查询、artifact 恢复和进程重启接管。Composite 仍由 M276 Coordinator 通过 `DomainRuntimeHost` allowlist 执行，公共 Runtime 不携带 GIS 或 Economic 策略。

用户应能提交一次包含多个已登记 Domain 组件的请求，立即获得稳定 `run_id`；随后通过同一语义 Application 查询状态、结果、artifact 和 evidence。进程重启或内存状态丢失后，不得重新调用模型或重复执行已完成组件，只能从 SQLite/artifact 恢复已保存的公共结果。

## Assumptions

1. Composite 请求继续使用 `spatial-agent.composite-request.v1`，组件依赖和 Domain allowlist 仍由 M275/M276 校验。
2. Composite 生命周期使用持久化作用域 `composite`，与 GIS、Economic 等 Domain 的运行记录隔离；`composite` 不是可被用户任意选择的 Domain Pack。
3. 现有 `AsyncApplication` 的异步提交、SQLite claim/recovery、内存 fallback、取消、超时和 observability 是唯一生命周期实现；Composite 不另写一套 worker 状态机。
4. 默认 CI/quick/stage 继续离线精简；真实 GIS、Economic、Docker 和 live 模型只在显式验收中执行。

## Commands

- Docker 定向测试：`docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m unittest tests.test_m278_composite_lifecycle tests.test_m256_http_application tests.test_m275_composite_contract tests.test_m276_composite_coordinator -v`
- Docker 编译：`docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m compileall -q agent production_api.py serve_api.py`
- Docker 架构门禁：`docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python scripts/architecture_check.py --strict`
- HTTP 显式验收：向 Docker `/composite-runs/async` 提交离线 GIS + Economic 请求，再轮询 `/composite-runs/{run_id}/observability` 和 `/composite-runs/{run_id}`。

## Project Structure

- `agent/models.py`、`agent/sqlite_store.py`：保存并恢复 canonical Composite Result。
- `agent/application/composite.py`：只负责 M276 组件协调，不承载持久化或 worker。
- `agent/application/composite_runs.py`：Composite 的同步持久化、AsyncApplication 注入、查询与恢复 Application seam。
- `agent/application/http.py`：新增 `composite_run_async`、`composite_observability`、`composite_run_detail`、`composite_evidence` 语义命令。
- `production_api.py`、`serve_api.py`：只保留 URL/状态码胶水，两个入口调用同一 HTTPApplication。
- `tests/test_m278_composite_lifecycle.py`：在 Application seams 验证幂等、持久化、artifact fallback 和恢复。

## Code Style

Coordinator 与生命周期分离：

```python
response = self._coordinator.run(request, session_id=session_id, run_id=run_id)
snapshot = self._snapshot(response, request=request, session_id=session_id)
self._state.save_run(snapshot)
return response
```

生命周期模块不得读取 URL、判断 GIS 工具名或直接创建 Domain Pack；Composite 结果必须通过 bounded schema normalize 后再进入 SQLite/artifact。

## Testing Strategy

- Envelope seam：验证 `AgentRunResult.to_dict()` 与 SQLite `_result_from_dict()` 保留 Composite Result，普通 GIS/Text 结果不改变。
- Lifecycle seam：使用 fake Coordinator 和临时 SQLite/artifact root，验证同步保存、异步 idempotency、状态轮询、artifact-only fallback、recovery claim 和失败 receipt；不调用真实模型。
- HTTP seam：验证 FastAPI/stdlib 都把语义命令交给同一个 HTTPApplication；不重复测试 transport 内部 if/elif。
- Docker gate：只运行 M278 定向测试、compileall、architecture strict 和必要的生产 health；不把 full test suite 作为默认路径。
- Live acceptance：后续显式验证真实 GIS + Economic Composite 的 async/restart 一致性，不进入默认 CI。

## Boundaries

- Always：复用 M275/M276/M277 schema；校验 Composite Result；使用 `AsyncApplication` 的幂等、claim、cancel、timeout、recovery；限制 run_id、artifact 引用和错误信息；记录结构化 evidence。
- Ask first：更改现有 Result/Async schema 版本、修改 SQLite 表结构、引入新运行时依赖或修改 CI 触发策略。
- Never：在 Composite 中复制 ToolRegistry/Planner/Runtime 循环；让 transport 直接调用 Domain Service；把组件原始异常、模型原文、密钥或宿主路径写入 public response；用重启重复执行已完成组件。

## Success Criteria

1. 同一个 Composite 请求可通过同步 Application 保存并通过 run detail 恢复 canonical `composite_result`。
2. 异步提交返回稳定 `run_id`，相同 idempotency key 不产生第二次组件执行；状态和结果可轮询。
3. SQLite 记录丢失但 artifact 存在时，run detail/evidence 能恢复 Composite Result，并明确标记 artifact recovery。
4. 进程重启后，孤儿 Composite async job 可被当前 worker claim；已完成组件不被重新执行，依赖失败/阻塞 receipt 保留。
5. FastAPI 和 stdlib 入口使用同一 HTTPApplication 语义命令，默认 Docker 门禁通过。
6. GIS、Economic 和 Composite 的公共 Result/Artifact/Evidence 契约保持领域隔离；不新增专题硬编码。

## Open Questions

- LLM 自动选择跨 Domain 组件和生成 Composite DAG 不在 M278 解决，待恢复契约稳定后单独做全局阶段。
- 前端 Composite 多面板动态渲染不在 M278 解决，但 HTTP 结果必须已可被通用 View renderer 消费。
