# M301 Planner-first 开放问题解析实施计划

## A：契约冻结与全局基线

- 以 capability map 和本 Spec 冻结 readiness、顶层阻断、组件级阻断、continuation 和 provider failure 状态矩阵。
- 只读取当前 Context Builder、Planner envelope、component handoff、continuation、View/Console 和对应精简测试；不批量加载历史文件。
- 先用一个通用测试替身证明“无关 Domain 缺失事实不阻断”。

## B：Context Builder readiness 投影

- 抽取领域中立的 facts readiness projection，统一 `complete/partial/missing/unavailable` 和 `blocking` 语义。
- 保持 Domain-owned facts/requirements，不在 Runtime 增加指标、区域或 GIS 关键词判断。
- 让 Planner envelope 携带最小 readiness、候选和缺失字段，继续执行字节预算和私有字段过滤。

## C：Planner-first 与 selected-component gate

- 调整规划前的顶层澄清条件，仅放行可安全供 Planner 选择的候选；不放行 `available=false` 或 `execution_ready=false`。
- 让已选组件复用现有 TaskPlan bridge、workflow 校验、component fact handoff 和 execution binding。
- 增加“选择后缺事实”“无候选”“不可用候选”“合法成功”四类精简契约。

## D：跨入口与用户投影

- 将 readiness 和阻断原因沿 planning response、HTTP、async/artifact/restart、Composite View 和 Console projection 传播。
- 统一 next action：补充字段、稍后重试、查看能力或重新提交；详细 trace/evidence 默认折叠。
- 对未知结果/缺失数据继续使用通用降级，不增加领域专用前端分支。

## E：集中验收

- Docker 中集中运行 M301 contract、M300 provider failure、M278 lifecycle、M294 binding、Node projection、compileall、architecture strict 和 readiness。
- 真实模型只执行一次显式开放请求；记录 provider/状态/是否创建 run/耗时分类，不保存 prompt、模型原文、密钥或私有数据。
- 若 live 仅出现 provider 波动，记录为外部失败，不改变安全门禁。

## F：交付与全局重规划

- 更新中文问题记录、任务账本、恢复快照和 milestones；确认恢复入口只列当前任务必要文件。
- 提交并推送阶段版本。
- 阶段完成后从产品、架构、数据、模型、部署、体验和测试七个维度重新规划，下一阶段优先验证至少一条真实跨领域成功链路。

## 风险与回滚

- 风险：放宽顶层澄清后模型选择无关能力。控制：候选 allowlist、execution-ready、TaskPlan 和 binding 门禁保持不变。
- 风险：readiness 字段使 envelope 膨胀。控制：内部 Context 与 provider Envelope 分层预算；内部默认 256 KiB，模型 Envelope 默认 96 KiB，只投影 readiness 摘要，超限仍 fail closed。
- 风险：旧客户端依赖 `request_facts_missing`。控制：保留错误码兼容投影，仅改变无关 Domain 不再提前阻断。
