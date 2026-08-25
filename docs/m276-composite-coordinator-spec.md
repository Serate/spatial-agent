# M276 Spec：Transport-neutral Composite Coordinator

## Objective

提供一个领域中立的 `CompositeApplication`，将 M275 的 Composite request 组件交给已启用的 Domain Runtime 执行，并将每个组件的结果通过同一个 Composite Result/Evidence 契约聚合。它解决“有了 Composite schema 但没有实际执行入口”的缺口，不复制 Agent Runtime 生命周期。

## 假设

1. 请求组件的 `domain_id` 已由上游选择器或用户确认提供；Coordinator 不接受任意模块路径，也不自行推断 Domain。
2. `DomainRuntimeHost.service()` 是唯一 Domain 实例获取边界；Coordinator 不访问 Domain Pack 内部实现。
3. 子请求通过现有 `AgentService.run()` 执行，返回同步公共 run payload；子请求的 planner/backend/workflow 由组件声明并受现有 Service/Runtime 校验。
4. 组件按请求声明顺序执行，但依赖必须已完成；未来可替换为拓扑排序或异步调度，不改变 Result/Evidence 契约。

## Application API

```python
application = CompositeApplication(host=domain_runtime_host)
response = application.run({
    "schema_version": "spatial-agent.composite-request.v1",
    "request": "组合分析",
    "components": [
        {
            "component_id": "space",
            "domain_id": "gis",
            "request": "查询区域边界",
            "planner": "rule",
            "backend": "memory",
        },
    ],
})
```

返回值是 transport-neutral JSON object：

- `status`：`COMPLETED`、`PARTIAL`、`BLOCKED` 或 `FAILED`。
- `result`：M275 的标准 `spatial-agent.result-envelope.v1`，`type=composite_result`。
- `components`：每个组件的有界执行 receipt，包含 `component_id`、Domain、状态、run id 摘要和错误码；不含模型原文、路径或完整请求。
- `result.composite`：统一的组件结果、data profile、View 和 Evidence 聚合。

## 生命周期

1. `resolve`：规范化 request，并通过 Host 选择每个 enabled Domain。
2. `dependency_gate`：检查依赖是否在本次请求中存在且已 `COMPLETED`；不可满足的组件转为 `BLOCKED`，不调用 Service。
3. `execute`：为组件创建有界 session id，调用对应 Service 的同步 `run`；异常转为 `FAILED` receipt，不中断其他无依赖组件。
4. `assemble`：把 child payload 交给 M275 `build_composite_result_contract`，将失败、阻塞和可用结果都保留。

Coordinator 自身不实现 retry、cancel、confirmation、LLM prompt 或 ToolRegistry dispatch；这些仍属于子 Runtime 的统一生命周期。

## Safety and boundaries

- Host allowlist 拒绝未知/禁用 Domain；Coordinator 不绕过 `DomainSelection`。
- 每个组件的请求、session、planner、backend、workflow 有界；组件 receipt 不回传原始异常和宿主路径。
- 依赖状态由 receipt 明确传播，不能把未执行组件伪装为成功。
- 组件结果的完整 artifact/evidence 仍由子 Service 管理；Composite 仅保存公共安全引用。

## Testing Strategy

- 使用 fake Host/Service 验证 allowlist 选择、执行顺序、依赖阻断、异常转换和统一聚合；不启动真实 GIS/模型。
- Docker 运行 M276 定向测试、M275 契约、compileall、architecture strict、quick/stage。
- HTTP/async/SQLite/artifact/restart 和真实 LLM/GIS/Economic 组合验收留到后续阶段。

## Success Criteria

1. 未知 Domain 在任何 Service 调用前被拒绝。
2. 无依赖组件按声明顺序执行；依赖失败或阻塞时下游不执行并得到 `BLOCKED` receipt。
3. 子 Service 异常被转换为有界失败 receipt，其他独立组件仍能执行。
4. 完成/部分/阻塞/失败组件最终都进入 M275 Composite Result/Evidence，且结果可通过 nested schema 校验。
5. 公共 coordinator 不导入 GIS/Economic，不修改 Runtime、Planner、ToolRegistry 或前端主流程。

## Non-goals

本阶段不承诺自动从自然语言生成跨域组件，不承诺跨域单一 SQLite run identity，也不承诺 HTTP 或 async transport 已接入。
