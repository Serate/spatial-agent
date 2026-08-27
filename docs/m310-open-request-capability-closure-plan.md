# M310 开放请求能力选择与数据语义闭合实施计划

## A：全局基线与事实需求矩阵

- 盘点 RequestFacts、capability requirements、component handoff、workflow resolver 和 planner evidence 的身份与状态边界。
- 冻结 `any/all/one` 及未知模式的兼容行为，覆盖缺失、歧义、ready 和不可用四类结果。
- 产出最小回放样本，不保存 provider 原文。

状态：已完成。

- 结果：新增领域中立 `agent/request_requirements.py`，统一归一化、`any/all/one` 满足判断和缺失字段投影；Composite context、component handoff、Planner envelope、discovery 和 workflow selection 不再丢失模式、候选值或约束键。
- 验证：Docker M310-A **5/5**，相邻需求/handoff/planner 回归 **26/26**，compileall 通过。

## B：模型选择到 Domain workflow 的闭合

- 检查 provider 选出的 capability 与 Domain discovery/candidate/workflow 是否一致。
- 让 Domain 只通过自身 resolver 补齐事实和约束；公共 bridge 只负责调用和统一分类，不猜测领域语义。
- 覆盖单组件、多组件、跨域和未绑定能力。

状态：已完成。

- 结果：Domain resolver 失败时不再回退 context workflow；resolver 返回的 workflow 必须具备身份并匹配 capability 的 `workflow_ids`；应用层区分不可用与未绑定状态。
- 验证：Docker M310-B 精简契约 **10/10**；未执行真实模型。

## C：TaskPlan 物化与失败分类

- 复用现有 canonical request、TaskPlan/DAG、ToolRegistry 和 execution binding 门禁。
- 明确 `clarification`、`preview_invalid`、`preview_failed` 和 `binding_failed` 的可读 evidence 与 run 创建边界。
- 验证有限 repair 不会改变 capability、事实或权限。

状态：已完成。

- 结果：复用 TaskPlan/DAG、ToolRegistry 和 execution binding 门禁，统一投影
  `clarification`、`preview_invalid`、`preview_failed`、`binding_failed` 和
  `rejected`；所有未验证计划均不会创建 execution run。
- 验证：Docker M310-C 精简契约 **12/12** 通过。

## D：数据 readiness 与结果证据

- 将字段、空间/时间对齐、覆盖范围和来源状态纳入 capability 的执行 readiness 投影。
- 结果不足或降级时保留事实和限制，不让答案生成器补造结论。
- 保持 Result/View/Artifact/Evidence 单一事实来源。

状态：已完成。

- 结果：新增领域中立 readiness 投影，保留字段、覆盖范围、空间/时间对齐、CRS、
  分辨率和来源状态；敏感路径、token、prompt 和模型响应不会进入公开 evidence。
  前端统一消费 `planning_failure` 和结构化证据，失败状态显示为用户可读文案。
- 验证：Docker M310-D 契约 **14/14**、Node projection smoke 通过。

## E：默认 Agent 用户体验与跨入口

- 检查默认模型路径的“理解—规划—执行—回答”阶段投影，结论优先，技术细节按需展开。
- 用通用结构化 View 展示澄清、计划、限制、证据和下一步，不增加领域专用前端分支。
- 对照 CLI、HTTP、async、artifact、SQLite/restart 的核心 identity。

状态：已完成。

- 结果：Console projection 能够展示等待补充、计划未生成和计划校验未通过，且不
  暴露内部错误码、工具名或 provider 原文；同步、异步、artifact 和恢复继续消费
  同一 Result/View/Evidence 投影。
- 验证：Docker Node projection、跨入口 identity、Service smoke 和 HTTP acceptance
  通过。

## F：Docker、live 与版本交付

- 在 Docker 中集中运行新增契约、相邻 Composite 回归、compileall、architecture strict、Node projection、Service smoke、生产 HTTP 和 readiness。
- 离线门禁通过后最多执行一次显式真实模型验收；固定 deadline、0 重试，按实际结果分类。
- 更新中文问题日志、milestones、工作快照和任务账本，提交并推送版本。

状态：已完成。

- 结果：重建 Docker 镜像并强制重建服务后，M310 契约、M309 相邻回归、compileall、
  architecture strict、Node projection、Service smoke、跨入口和真实本地 GIS HTTP
  验收通过；`/health/ready` 返回 200 且 local GIS/live 配置可用。
- 真实模型：本阶段唯一一次显式调用实际到达 provider，structured output 通道成功，
  模型返回结构化 `NEEDS_CLARIFICATION`，未创建 execution run；按语义澄清记录，未
  将其冒充为真实执行成功。

## 交付顺序

`A → B → C → D → E → F`（已完成）

测试按独立失败模式合并到阶段收口，不随任务数量线性增加；实现过程保持串行。
