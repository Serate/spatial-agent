# M328 Capability Map：受控开放行动闭环

## 全局判断

M327 已完成能力描述、能力选择解释和跨类型结果摘要。下一阶段不再增加固定专题或大量工具，
而是把“模型选择行动 → 受控执行 → 外部证据 → 人工决策 → 可恢复完成”这一条通用闭环补齐。
GIS、经济和公开网页只是验收载体，公共 Runtime 不携带领域分支。

## 七维度范围

| 维度 | M328 关注点 | 不做什么 |
|---|---|---|
| 产品 | 用户能看懂搜索来源、等待审批、继续/拒绝和降级结论 | 不增加专题页面 |
| Runtime | ReAct 行动、审批、恢复、取消和结果完整性共享生命周期 | 不绕过 Registry/Policy |
| Domain | 既有 GIS、经济、指标能力可组合并提供统一证据 | 不复制 Domain workflow |
| 数据 | 数据集、网页来源和 freshness/不可用状态可追溯 | 不自动下载未知数据 |
| 模型 | 真实模型选择工具、搜索或提案时保持结构化输出 | 不保存思维链或模型原文 |
| 部署 | Docker GIS、Web 搜索白名单和无网络 sandbox 可重复验收 | 不默认扩大网络权限 |
| 体验/验证 | 流式答案、阶段事件、审批等待与最小充分测试 | 不把 live 测试放入默认 CI |

## 阶段边界

- Always：Capability Catalog、ToolRegistry、schema、Execution Policy、审批、数据 readiness 和 evidence。
- Ask first：新增网页域名、替换搜索服务、改变 proposal Schema 子集、引入新的运行时依赖。
- Never：自动发布/执行未审批工具、执行模型提供的任意 URL/命令/代码、伪造网页来源、传播 Prompt 或隐藏思维链。
