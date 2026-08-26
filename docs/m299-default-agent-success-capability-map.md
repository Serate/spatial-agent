# M299 默认 Agent 成功路径能力图

本阶段从项目全局目标审视“默认真实 Agent 已开启但成功率和可理解性仍不足”的问题。重点是让已有能力更容易被 Planner 安全组合，不新增 GIS、经济或区域专用流程。

| 模块 | 职责 | 依赖 |
|---|---|---|
| `planner-envelope` | 统一 Planner-facing context 的层级、预算、脱敏和版本边界 | `analysis-discovery`、Result profile |
| `selection-evidence` | 记录请求事实、候选能力、选择理由和澄清状态的可读摘要 | `planner-envelope`、RequestFacts |
| `agent-stage-projection` | 将 discovery、planning、clarification、execution 和 answer 映射为用户阶段 | `selection-evidence`、Result/View |
| `cross-entry-acceptance` | 对照 CLI、HTTP、同步/异步、artifact/restart 和显式 live 的核心 identity | `planner-envelope`、execution binding |

依赖方向：

`planner-envelope` → `selection-evidence` → `agent-stage-projection`；
`planner-envelope` 与 execution binding 共同供 `cross-entry-acceptance` 使用。

## 全局约束

- Planner 只能选择能力目录中已登记、可校验、可执行的能力；压缩上下文不能丢失选择所需的身份、数据形态和执行就绪状态。
- 目录投影、Context Builder、LLM Planner 和 provider payload 使用统一的有限预算；超限时返回结构化可恢复状态。
- “未声明 discovery”“数据未知”“数据不可用”“模型澄清”和“计划拒绝”保持可区分，前端不得把它们合并为一个失败提示。
- 默认产品继续使用 `openai + local`；`rule + memory` 只作为显式离线验收路径。
- 不暴露 prompt、模型原文、思维链、密钥、私有路径或未经登记的数据源。

## 构建顺序

1. 冻结默认 Agent 成功/澄清/不可用的跨入口验收矩阵和统一上下文预算。
2. 实现紧凑、分层的 Planner context 投影，保持候选能力和 Result profile 的可发现性。
3. 补充选择与澄清 evidence 的可读摘要，复用现有生命周期和恢复契约。
4. 让前端阶段条消费真实结构化状态，并验证降级文案与下一步动作。
5. 在 Docker 真实数据上做 Replay/Rule 对照与一次显式 live，完成跨入口收口。
