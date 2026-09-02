# 当前任务状态

> 热状态文件，只保留当前阶段、进行中任务、必要文件和最近验证。历史过程按需从阶段 handoff 或归档读取。

## 当前阶段

- 阶段：`M336` HTTP 入口收敛
- 当前任务：M336-D FastAPI 传输适配器交付与提交前核对
- 状态：M336-A～D 已实现并完成 Docker 定向验收，下一步提交推送
- 基线：`bd94880`
- 协作：单 Agent，最大并发度 1；测试、GIS 和 live 验收优先使用 Docker

## 当前必要文件

- `docs/stages/M336/{capability-map.md,spec.md,plan.md,handoff.md}`
- `agent/application/http_composition.py`
- `agent/application/stdlib_http.py`
- `production_api.py`
- `serve_api.py`
- `agent/application/http.py`
- `agent/application/http_routes.py`
- `agent/application/http_transport.py`
- `agent/application/fastapi_http.py`
- `tests/test_m78_http_contract.py`
- `tests/test_m10_api_service.py`
- `tests/test_m60_runtime_capabilities_contract.py`
- `tests/test_m165_cross_entry_contract.py`
- `agent/evidence/{contract.py,projection.py,registry.py}`
- `agent/evidence/{bundle.py,composite.py,identity.py,quality.py}`
- `agent/runtime_core/{run_budget.py,progress.py,react_runtime.py}`
- `agent/network/{web_search.py,web_fetch.py}`
- `tests/test_m334_evidence_quality.py`
- `docs/agent-work-state.md`

## 当前决策

- M333 已推送：`722db01`；默认 Web 模式仍为 `allowlist`，`public` 必须显式开启。
- M336：FastAPI 是 canonical 入口；stdlib 仅作本地兼容适配，二者共享 Composition Root、HTTPApplication、route metadata 和 transport error projection。
- M334 只建设通用证据身份、质量、Bundle 和跨域 Composite；不引入 RAG、不持久化网页正文、不自动裁决冲突来源。
- 旧 Evidence payload 必须可读取；缺失时间表示 `unknown`，不能默认新鲜。

## 最近验证

- M334：受影响回归 `56/56`；Docker `quick + stage + smoke`、compileall、architecture strict、readiness `200` 和生产 HTTP acceptance 通过。
- 真实模型 + 本地 GIS + `public` 网页请求实际执行 3 个工具步骤，但 Provider 在有界预算内未完成；已记录 `provider_timeout`/网络不可用安全降级。
- 历史回归专项：M163/M66 的 artifact 恢复、动态 Runtime 注入、几何证据和跨入口身份归一化已修复；Docker 定向回归 `4/4` 通过。

## 下一步

- M334-A～E 已完成；阶段交接、中文问题日志、代码/文档索引已更新，待提交推送。
- 提交后进入 M335，优先处理 Provider/网络健康、通用多工具 ReAct、多结果组合、数据对齐和全局实时体验。
- M163/M66 修复已完成；本轮 HTTP 定向回归同时覆盖历史兼容 seam，不扩大为默认全量回归。

## M336 收口记录

- 实现：`http_composition.py` 统一运行时装配；`stdlib_http.py` 承担标准库 URL/query/JSON、artifact、SSE、静态资源和错误投影适配；`serve_api.py` 缩为薄入口。
- 修复：显式 artifact root、`max_files` 范围和每请求 Service 重绑定；旧测试改为显式离线 planner/backend，避免真实模型网络造成非确定性超时。
- 验证：Docker 相关回归 `30/30`，compileall 通过，`/health/ready` HTTP 200，diff check 通过。
- 下一步：提交推送阶段版本；推送后基于全局目标重新规划，不读取无关阶段历史。

## M336-D 收口记录

- `agent/application/fastapi_http.py` 集中 FastAPI 的依赖解析、共享分发、错误投影、SSE 和 artifact 响应；生产入口保留兼容路由函数但不复制传输实现。
- Domain Routing catalog/select/override/clear 通过共享 route metadata 与 `HTTPApplication` 分发。
- Docker 定向 HTTP/Domain Routing/SSE/artifact 回归 `17/17` 通过；扩展 Composite/跨入口回归共 36 项，其中 `35` 项通过、`1` 项因容器无 PowerShell 跳过。
- `compileall` 通过；现有容器持久化状态导致的 M150 session 绑定错误和容器缺少 PowerShell 的跳过项不归因于本次改动。
