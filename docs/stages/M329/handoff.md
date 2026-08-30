# M329 阶段交接

## 状态

- 阶段：`M329` 通用请求路由与跨域能力汇聚
- 状态：已完成
- 基线：`81e79ab feat: close M328 controlled open actions`
- 协作：单 Agent，最大并发度 1；Python、GIS、测试和验收优先使用 Docker

## 当前目标

让 `/runs`、CLI 和前端默认进入通用 Runtime。模型可直接回答任意普通问题，也可按需调用已登记的跨领域工具、白名单 Web 或受控工具提案；显式 `/domains/{id}` 保持领域强制模式。

## 已完成

- M329 capability map、Spec、Plan 已建立。
- M328 的 ReAct、Web evidence、proposal approval、答案流、SSE、Artifact 和恢复契约作为复用基线。
- 热状态已收敛到当前阶段，恢复默认不加载完整历史。
- M329-A 已新增 `spatial-agent.request-mode.v1`；Result、SQLite 恢复、execution record 和终态事件已接入。
- Docker M329-A 紧凑测试 `4/4` 通过。
- M329-C-2 已完成：真实 DeepSeek + Docker 验证普通通用回答、跨域经济工具链、白名单 Web 搜索不可用降级和受控 Python
  工具提案；ReAct 状态、工具计数、结果类型和降级 reason code 均符合公共契约。
- M329-D 已完成：新增 `AgentService(general=True)` 产品模式；production FastAPI、stdlib 服务和 CLI 的默认入口使用通用
  Runtime，显式 `/domains/{id}` 服务与旧 `/runs/auto` 继续隔离。同步、preview、async、events 和 Artifact 已完成 Docker
  验证。
- M329-E/F 已完成：SQLite/Artifact 重启、多轮会话、SSE `Last-Event-ID`、通用 proposal 同一 Run 恢复、显式 Domain 隔离、
  Docker 精简回归、readiness、compileall、architecture/index 和前端 smoke 均通过。答案生成上下文已修复“仍在执行”的错误
  用户表述，真实模型复验通过。

## 当前任务

- M329-B 已完成：新增 `GeneralCapabilityHost`，聚合已登记 Domain Pack 的能力、工具、结果类型、权限和健康状态；
  工具按唯一 owner dispatch，Domain preflight 沿同一 owner 转发，单 provider 失败只产生局部 degraded。
- M329-B 的实际声明冲突 fail-closed；兼容性结果注册表中未被能力、工作流或工具输出引用的旧条目不进入 Host 公共结果平面，
  避免遗留元数据制造假冲突。
- 阶段任务已完成，下一阶段为 M330；恢复时只读取 M330 工作快照、M330 handoff 和必要源码。

## 必要文件

- `agent/models.py`
- `agent/runtime_core/run_lifecycle.py`
- `agent/runtime_core/react_runtime.py`
- `agent/persistence/sqlite_store.py`
- `agent/application/run.py`
- `agent/application/run_recovery.py`
- `agent/run_events.py`
- `agent/request_mode.py`
- `agent/execution_contract.py`
- `agent/runtime_factory.py`
- `agent/domain_registry.py`
- `agent/tool_provider.py`
- `agent/general_capability_host.py`
- `agent/tools.py`
- `agent/runtime_core/planning_surface.py`
- `domains/*/domain.py`

## 验证与阻塞

- M328 已有 Docker/live 验收基线；M329-A Docker 紧凑测试 `4/4` 通过。
- 验证：Docker 重建后 M329 Host/Request Mode 紧凑回归 `8/8`；内置 GIS、文本、指标、经济四域聚合 `22` 个工具、`32` 个能力、
  `31` 个实际结果类型，健康状态 `ready`；ToolRegistry owner dispatch 实际调用文本与经济 provider。
- M329-C-1 已完成：新增 `GeneralRuntimePack`、`GeneralResultRegistry` 和 `build_general_runtime`；通用 Runtime 使用聚合
  Host、合并 Domain Facts/discovery、保留领域结果 View owner 路由，并提供无 GIS 专用分支的离线 fallback。
- 阻塞：无。

## 已完成任务（M329-C-2 / M329-D / M329-E / M329-F）

- 默认真实模型使用 full ReAct；Web 仅允许配置白名单，工具提案仍需 Docker sandbox 和人工审批。
- 产品默认 `/runs`、preview、async、events、Artifact 和 CLI 使用 `general` Runtime；显式 `/domains/{domain_id}` 不变。
- 兼容修正：Host provider 不可用时，descriptor 的 `availability` 保持对象契约，避免 planner context 投影崩溃；Host 暴露公开
  `backend_name` 属性，General Pack 不再读取 Host 私有字段。
- `build_answer_context` 将答案生成期间的内部 `EXECUTING` 投影为有界 `FINALIZING`，同时标记执行事实已完成，避免答案模型
  把内部状态写成用户仍需等待的结论。
- 交付门禁：Docker M329/M328 相关回归 `18/18`，答案定向回归 `15/15`；compileall、architecture strict、readiness `200`、
  code/document index 和前端 projection smoke 通过。
- 不读取：M327/M328 完整历史、模型原文、Prompt、密钥和全量测试。
