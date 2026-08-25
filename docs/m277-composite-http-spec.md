# M277 Spec：Composite HTTP 统一入口

## Objective

提供一个稳定的同步 HTTP 入口 `/composite-runs`，通过既有 `HTTPApplication` 调用 `CompositeApplication`。GIS、Economic 或未来 Domain 的组件都只能出现在请求契约中，HTTP 层不携带领域策略。

## Commands

- Docker 定向：`docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m unittest tests.test_m256_http_application tests.test_m275_composite_contract tests.test_m276_composite_coordinator -v`
- Docker profile：`docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python scripts/test_profile.py --profile ci --profile stage`
- HTTP live contract：对运行中的 `http://127.0.0.1:8088/composite-runs` 提交一个 GIS + Economic 的离线/本地数据请求，检查 `status/result.type/data_profile/views`。

## Project Structure

- `agent/application/http.py`：新增语义命令 `composite_run`。
- `agent/application/composite.py`：M276 Coordinator，HTTP 不复制其执行逻辑。
- `production_api.py`、`serve_api.py`：只增加共享 `/composite-runs` 路由和 Composition Root 注入。
- `tests/test_m256_http_application.py`：Application dispatch contract。
- `docs/m277-composite-http-*`：能力图、Spec、Plan。

## Code Style

HTTPApplication 只接收已解析的 dict 并调用 application seam：

```python
if action == "composite_run":
    return self._composite.run(body, session_id=session_id)
```

不读取 URL、不判断 Domain、不扫描组件工具名。

## Testing Strategy

- 离线契约：验证 HTTPApplication 分发、Composite Result nested schema 和错误边界。
- Docker 生产启动：验证 FastAPI import/health，避免 composition root 初始化错误。
- 显式 HTTP：验证真实 Docker 中 GIS + Economic 同步组合和组件失败状态；不调用真实模型。
- stdlib/FastAPI 语义一致性：两者都必须调用同一 HTTPApplication action，不各自实现结果聚合。

## Boundaries

- Always：共享 `HTTPApplication` 和 `CompositeApplication`；错误保留稳定 `error_code`；结果沿用 M275/M276 schema。
- Ask first：改变 `/composite-runs` 请求/响应版本、接入持久化或异步生命周期。
- Never：在 transport 中创建 Domain Pack、直接调用 ToolRegistry、复制组件循环或泄露宿主路径/模型原文。

## Success Criteria

1. FastAPI 和 stdlib HTTP server 均可路由 `/composite-runs` 到同一 semantic command。
2. 合法 GIS + Economic 请求返回 `composite_result`，并保留每个组件的结果类型、profile、View 和 evidence。
3. 组件失败仍返回结构化 Composite 状态，不被 HTTP 层改写成无意义字符串。
4. 生产 Docker 启动健康，默认 CI/stage 离线通过。

## Non-goals

本阶段不提供 Composite run 查询、artifact 下载、async 提交或重启恢复；这些必须作为下一阶段统一生命周期设计的一部分接入。
