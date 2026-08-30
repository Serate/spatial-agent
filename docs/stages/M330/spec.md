# M330 Spec：通用 Agent 开放问题质量与纵向行为验收

## 目标

让 M329 的 general Runtime 在真实使用中体现 Agent 行为，而不是只表现为固定数据查询器。系统必须优先尝试合理的
通用回答或受控行动；当能力、事实或环境不足时，返回可理解的澄清/降级结果，而不是无根据地声称完成。

## 行为契约

- `general` 是产品默认 Runtime；显式 Domain 入口继续保持隔离。
- Planner 只能从公共 Capability Catalog、已注册 ToolRegistry、白名单 Web 和受控 proposal 能力中选择行动。
- 直接回答可以不产生工具步骤；需要外部事实时必须产生可审计的工具或 Web evidence。
- 多步行动每一步都必须经过 schema、权限、数据 preflight 和执行策略校验。
- provider 失败、数据缺失、网络不可用和结果部分完成必须进入统一 Result/Evidence/RunEvent 投影。
- 工具提案只能形成待审批状态；批准后恢复原 Run，拒绝、过期或撤销必须安全终止。
- 答案模型只能看到有界、脱敏、已完成的事实；不能把内部 `EXECUTING`、工具名或引用写成用户结论。
- SSE、轮询、Artifact、CLI 和前端消费同一结果身份、证据状态和事件序列。

## 用户答案要求

答案优先给出一句结论，再给关键依据和限制；普通用户不需要理解 planner、provider、fingerprint 或 result_ref。数据不足时
必须说清楚“已查到什么、缺什么、下一步能做什么”。过程摘要默认收起，不显示隐藏思维链。

## 验收边界

首版至少覆盖：无数据普通问题、单域事实、跨域多步、白名单 Web、未登记能力/工具提案、provider 降级、澄清、多轮续问、
SQLite/Artifact 重启和 SSE 断线续传。真实模型与 Docker 是显式验收，不进入默认 CI。

## 安全边界

始终保留 allowlist、ToolRegistry schema、权限、执行预算、网络白名单、Docker sandbox、人工审批和脱敏 evidence；不提供任意
网络访问、任意 shell、凭据处理、数据外传或自动上线能力。
