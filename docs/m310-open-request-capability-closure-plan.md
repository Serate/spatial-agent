# M310 开放请求能力选择与数据语义闭合实施计划

## A：全局基线与事实需求矩阵

- 盘点 RequestFacts、capability requirements、component handoff、workflow resolver 和 planner evidence 的身份与状态边界。
- 冻结 `any/all/one` 及未知模式的兼容行为，覆盖缺失、歧义、ready 和不可用四类结果。
- 产出最小回放样本，不保存 provider 原文。

状态：待开始。

## B：模型选择到 Domain workflow 的闭合

- 检查 provider 选出的 capability 与 Domain discovery/candidate/workflow 是否一致。
- 让 Domain 只通过自身 resolver 补齐事实和约束；公共 bridge 只负责调用和统一分类，不猜测领域语义。
- 覆盖单组件、多组件、跨域和未绑定能力。

状态：待开始。

## C：TaskPlan 物化与失败分类

- 复用现有 canonical request、TaskPlan/DAG、ToolRegistry 和 execution binding 门禁。
- 明确 `clarification`、`preview_invalid`、`preview_failed` 和 `binding_failed` 的可读 evidence 与 run 创建边界。
- 验证有限 repair 不会改变 capability、事实或权限。

状态：待开始。

## D：数据 readiness 与结果证据

- 将字段、空间/时间对齐、覆盖范围和来源状态纳入 capability 的执行 readiness 投影。
- 结果不足或降级时保留事实和限制，不让答案生成器补造结论。
- 保持 Result/View/Artifact/Evidence 单一事实来源。

状态：待开始。

## E：默认 Agent 用户体验与跨入口

- 检查默认模型路径的“理解—规划—执行—回答”阶段投影，结论优先，技术细节按需展开。
- 用通用结构化 View 展示澄清、计划、限制、证据和下一步，不增加领域专用前端分支。
- 对照 CLI、HTTP、async、artifact、SQLite/restart 的核心 identity。

状态：待开始。

## F：Docker、live 与版本交付

- 在 Docker 中集中运行新增契约、相邻 Composite 回归、compileall、architecture strict、Node projection、Service smoke、生产 HTTP 和 readiness。
- 离线门禁通过后最多执行一次显式真实模型验收；固定 deadline、0 重试，按实际结果分类。
- 更新中文问题日志、milestones、工作快照和任务账本，提交并推送版本。

状态：待开始。

## 交付顺序

`A → B → C → D → E → F`

测试按独立失败模式合并到阶段收口，不随任务数量线性增加；实现过程保持串行。
