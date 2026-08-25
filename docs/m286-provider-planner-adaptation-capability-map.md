# M286 中转模型 Planner 适配能力图

## 阶段定位

M285 已证明开放式 Composite 候选可以经过 `TaskPlan/DAG → ToolRegistry → Runtime` 的统一安全门控，并能沿 HTTP、async、artifact 和 restart 保留结构化证据。M286 的问题不是继续增加 GIS 或经济工具，而是让真实中转模型更稳定地选择已登记能力并返回可校验的组合计划。

本阶段仍服务于通用 Agent Goal：provider 是可替换基础设施，模型只提出候选，公共应用层负责规范化、能力 allowlist、TaskPlan 门控和生命周期。任何模型输出无法证明合法时，都必须澄清或拒绝。

## 七维度全局盘点

| 维度 | 当前证据 | M286 缺口 | 阶段产出 |
| --- | --- | --- | --- |
| 产品 | 用户可看到计划来源、阶段和证据 | 真实中转失败时缺少清晰的“模型不可用/需澄清”反馈 | 有界失败原因和可恢复下一步 |
| 架构 | Rule/Replay/LLM 共享 context、canonical plan 和 TaskPlan bridge | provider 格式兼容与能力身份投影还不够稳定 | provider adapter 与 identity projection seam |
| 数据 | context 已投影数据就绪、工具和结果类型 | 模型不能看到或不应看到路径/原始数据 | 只增加安全身份提示，不扩展数据权限 |
| 模型 | provider probe 已 READY；Composite live 仍四类安全拒绝 | 输出字段、状态、精确 capability identity 不稳定 | 有界格式兼容、选择提示和错误分类 |
| 部署 | Docker/live harness 可单请求、有 deadline、脱敏 | 复杂 live 输出预算需要可控参数 | 单次可复现 live receipt |
| 体验 | 前端消费结构化 plan/evidence | 失败信息需要区别 provider、schema、能力和数据状态 | 通用 planner failure view 投影 |
| 测试 | replay 与跨入口 contract 已覆盖核心门控 | 不能用大量 live 重试掩盖问题 | 少量独立失败模式 + 一次显式 live |

## 能力边界

### 本阶段建设

1. 给模型提供可复制的 `domain_id + capability_id` 精确身份和最小工具/结果提示。
2. 在 provider adapter 层支持少量有文档的 JSON 包装/别名兼容，并保留 unknown-field fail closed。
3. 将 provider、context、Planner schema、capability allowlist、TaskPlan policy 和 execution gate 的失败分类稳定化。
4. 让失败结果沿现有 HTTP、async、artifact、restart 和前端 projection 保持一致。
5. 用脱敏 replay 覆盖成功、字段漂移、非成功携带组件、未知能力和不可用能力；真实中转只做单次显式验收。

### 明确不做

- 不新增专题工具、数据源、RAG、外部搜索或 MCP 运行时依赖。
- 不接受任意字段、任意 wrapper、未知 Domain/capability、未经校验的工具或跨域组件。
- 不在 Runtime、ToolRegistry、GIS/Economic Domain 或前端添加 provider 专用分支。
- 不保存或输出 prompt、模型原文、密钥、请求头、私有路径和完整上下文。

## 交付切片

M286 作为一个完整能力阶段推进，集中覆盖：契约设计 → context/adapter 实现 → planner application 集成 → 跨入口失败投影 → 精简回放 → Docker/live 验收 → 中文文档和版本交付。
