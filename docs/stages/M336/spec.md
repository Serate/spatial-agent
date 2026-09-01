# Spec：M336 HTTP 入口收敛

## Objective

将 `production_api.py` 和 `serve_api.py` 收敛为同一套 HTTP 语义与运行时装配。FastAPI 是产品 canonical 部署入口；标准库入口保留本地 GIS、旧脚本和历史测试所需的兼容能力，但只承担框架适配，不再复制 Composition Root、业务路由或错误契约。

## Commands

- Docker 定向测试：`docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m78_http_contract tests.test_http_contract -v`
- 入口兼容测试：`docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m10_api_service tests.test_m60_runtime_capabilities_contract tests.test_m165_cross_entry_contract -v`
- 编译检查：`docker exec ai-agent-spatial-agent-1 python -m compileall -q agent production_api.py serve_api.py`
- 服务检查：`Invoke-WebRequest -Uri http://127.0.0.1:8088/health/ready -UseBasicParsing`

## Project Structure

- `agent/application/http_composition.py`：唯一运行时装配模块。
- `agent/application/stdlib_http.py`：标准库兼容适配器。
- `agent/application/http.py`、`http_routes.py`、`http_transport.py`：公共语义、路由和传输投影。
- `production_api.py`：FastAPI canonical Composition Root/部署入口的薄适配层。
- `serve_api.py`：本地兼容启动入口，仅导出兼容名称并启动 stdlib adapter。

## Interface and Code Style

框架适配器只接收解析后的 `RouteMatch`、query/body 和 `HTTPApplication`，通过公共 `dispatch_read` / `dispatch_execute` 执行语义 action。错误必须统一调用 `error_projection`；路径参数必须由 `resolve_route` 或共享 artifact path resolver 处理。

```python
match = resolve_route("POST", parsed.path)
if match is None:
    return self._write_not_found()
result = application.execute(
    match.action,
    body,
    run_id=match.resource_id,
    template_id=match.template_id,
)
```

## Testing Strategy

- 默认只运行受影响的 HTTP contract 和 stdlib 兼容测试。
- 入口收敛必须验证：共享 action、错误状态、域路由、artifact 安全路径和 SSE 事件入口。
- Docker 负责编译、服务 readiness 和集成验证；真实模型不属于本阶段默认测试。
- 不为保留旧 import 而复制生产实现；兼容名称可以 re-export，行为必须走公共适配器。

## Boundaries

- Always：保持 `HTTPApplication`、`RunEvent`、Result/Evidence 契约不变；统一错误状态和路径安全检查。
- Ask first：删除 `AgentApiHandler` 或改变现有 CLI/HTTP URL；升级 FastAPI 或新增生产依赖。
- Never：在任一入口重新加入 GIS 专用业务分支；绕过公共 route table；提交密钥或运行产物。

## Success Criteria

1. 两个根入口不再分别创建 Host、Service、Routing 和 Composite 运行时。
2. 新增共享 HTTP route 时只需修改一处语义 route metadata。
3. FastAPI 与 stdlib 对同一 action 产生一致的核心结果、错误码和 evidence。
4. `serve_api.py` 仅保留启动和兼容导出，不再包含大段 if/elif 业务分派。
5. 旧的 `AgentApiHandler` 调用方仍可运行，并明确标记为兼容适配。
