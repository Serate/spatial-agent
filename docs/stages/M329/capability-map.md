# M329 Capability Map：通用请求路由与跨域能力汇聚

## 目标

让普通用户请求默认进入通用 Agent Runtime，由真实模型按需决定直接回答、调用已注册工具、搜索白名单网页、组合多步行动、提出受控工具提案或请求澄清。GIS、经济、指标和文本能力只是可插拔 Domain Pack。

## 模块与依赖

| 模块 | 职责 | 依赖 |
|---|---|---|
| request-mode-contract | 统一 answer/execute/mixed/clarify 模式与结果投影 | Runtime Result |
| general-capability-host | 汇聚 Domain Pack 能力、工具、权限、健康状态和 owner dispatch | DomainRegistry、ToolRegistry |
| general-runtime-adapter | 提供领域中立的 Context、preflight、Result Registry 和 fallback | general-capability-host、AgentRuntime |
| product-entrypoint | 将 HTTP、CLI、前端默认入口切换到通用 Runtime | general-runtime-adapter |
| recovery-compatibility | 会话、SQLite、Artifact、SSE、审批恢复保持同一 identity | product-entrypoint、现有持久化 |
| acceptance-and-handoff | 精简测试、Docker/live 验收、索引和交接 | 全部模块 |

构建顺序：request-mode-contract → general-capability-host → general-runtime-adapter → product-entrypoint → recovery-compatibility → acceptance-and-handoff。

## 边界

- 通用模块只依赖 Domain Pack/Provider 接口，不导入 GIS、经济或其他具体实现。
- 所有工具仍须经过 ToolRegistry、schema、权限、数据 readiness 和审批门禁。
- 网络只允许配置的 HTTPS 白名单；工具提案只允许沙箱校验后人工审批。
- 不引入 RAG、任意 URL/命令/代码执行，也不保存 Prompt、模型原文或隐藏思维链。
