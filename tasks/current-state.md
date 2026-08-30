# 当前任务状态

> 热状态文件，只保留当前阶段、进行中任务、必要文件和最近验证。

## 当前阶段

- 阶段：`M330`
- 当前任务：M330-A 通用直接回答场景矩阵
- 状态：M330-A 进行中；先固定公共行为契约，再做最小实现与验证
- 基线：`81e79ab`
- 协作：单 Agent，最大并发度 1；测试、GIS 和 live 验收优先使用 Docker

## 已完成

- M328 受控开放行动闭环已完成并提交：ReAct、Web evidence、工具提案审批恢复、答案流、SSE、Artifact 和 Docker/live 验收。
- M329 capability map、Spec、Plan、handoff 已建立。
- M329-0 已完成热状态和恢复入口收敛。
- M329-A 已完成：`request-mode.v1` 已接入 Result、SQLite/artifact、execution record 和终态事件。
- M329-B 已完成：`GeneralCapabilityHost` 聚合四个已登记 Domain Pack，按 owner dispatch 和 preflight，局部 provider 失败降级，
  工具/实际结果类型冲突 fail-closed，并提供稳定上下文指纹。
- M329-C-1 已完成：`GeneralRuntimePack`/`GeneralResultRegistry`/`build_general_runtime` 已接入聚合 Host；规则模式可完成诚实
  direct-answer fallback，通用 Runtime 仍不携带 GIS 专用策略。
- M329-C-2 已完成：默认 full ReAct、白名单 Web 搜索和受控工具提案在 Docker 中通过真实模型验收；普通回答、经济工具链、
  Web 不可用降级和 proposal `WAITING_FOR_DECISION` 均保持统一生命周期与安全边界。
- M329-D 已完成：产品 HTTP/CLI 默认进入通用 Runtime；同步、preview、异步、事件和 Artifact 返回 `general` 身份，
  `/domains/{domain_id}` 继续使用显式 Domain Runtime。
- M329-E/F 已完成：SQLite/Artifact 重启、多轮会话、SSE `Last-Event-ID`、proposal 同一 Run 恢复、显式 Domain 隔离、
  Docker/真实模型/索引/前端阶段门禁全部通过；答案生成上下文不再把内部执行状态写成用户仍在等待。

## 进行中

- M330-A：建立概念解释、比较、总结、写作、简单计算等非数据请求矩阵；确认通用 Runtime 不依赖关键词即可直接回答。

## 必要文件

- `docs/stages/M329/{capability-map.md,spec.md,plan.md,handoff.md}`
- `agent/runtime_factory.py`
- `agent/domain_registry.py`
- `agent/domain_contract.py`
- `agent/tool_provider.py`
- `agent/tools.py`
- `agent/runtime_core/planning_surface.py`
- `domains/*/domain.py`
- `domains/*/provider.py`

## 验证

- M328 Docker 紧凑回归、readiness、compileall、architecture/index、SSE/Artifact/live 基线已通过。
- M329 Host/Request Mode/General Runtime 紧凑测试 `10/10`，答案上下文与相邻回归 `15/15`，阶段收口回归 `18/18`；真实模型
  普通回答、经济工具链、Web 降级、工具提案和同一 Run 恢复均完成；Docker HTTP 默认通用入口、显式 Domain、preview、async、
  events、Artifact、SSE 续传和前端 smoke 验证通过。

## 阻塞与下一步

- 阻塞：无；Docker GIS provider 因当前挂载数据不完整保持局部 unavailable，通用 Runtime 已按契约降级，未影响经济、指标、
  文本和通用直接回答。
- 下一步：完成 M330-A 紧凑契约与显式真实模型验收后，进入 M330-B 开放请求与能力发现。
