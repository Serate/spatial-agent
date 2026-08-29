# Capability Map：M327 开放请求能力发现与结果质量

M326 已解决开放 ReAct 的增量动作策略边界和部分结果语义。M327 从项目整体目标出发，继续补齐
“模型能发现什么、为什么选择、用户最后看懂什么”这条产品链，不新增 GIS 专题分支。

| 模块 ID | 职责 | 依赖 |
|---|---|---|
| `capability-descriptors` | 将能力的输入事实、输出类型、前置条件、成本和证据要求投影为可组合目录 | 现有 Capability Catalog、Result profile |
| `selection-explanation` | 记录模型/规则选择的能力、未选候选、缺失事实和用户可见的选择摘要 | `capability-descriptors`、RequestFacts、Execution Policy |
| `result-synthesis` | 根据结构化 Result/View/Evidence 动态生成跨类型摘要、限制和下一步 | Result completeness、Evidence projection |
| `cross-entry-acceptance` | 验证 CLI、HTTP、前端、Artifact 和恢复消费同一能力/结果身份 | 前三个模块、Run lifecycle |

构建顺序：`capability-descriptors` → `selection-explanation` 与 `result-synthesis` →
`cross-entry-acceptance`。

边界：公共 Runtime 只消费通用契约；Domain Pack 提供能力描述和数据适配器；模型不能绕过
ToolRegistry、权限、审批、网络白名单、数据就绪或结果契约。
