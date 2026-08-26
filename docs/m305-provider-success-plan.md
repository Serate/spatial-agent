# M305 Provider-backed 成功率与可恢复交互实施计划

## A：全局基线与成功率矩阵

- 从产品、架构、数据、模型、部署、体验、测试七个维度冻结成功、澄清、拒绝、provider failure 和执行失败的边界。
- 以 M304 provider runtime evidence 为基线，测量阶段 Envelope 大小、输出预算、deadline 和失败类别的贡献。
- 只读取当前任务必要源码和精简 replay，不读取模型原文、密钥或历史全量日志。

## B：请求预算与 Provider Attempt receipt

- 统一 provider/harness deadline、输出预算、attempt/retry 计数和阶段标识。
- 已落地公共 `spatial-agent.planner-attempt.v1` receipt 的安全构建与幂等投影，包含 Envelope 实际字节数、输出/期限预算、repair lineage 和统一动作 ID。
- 保持产品默认 `openai + local`；离线 Rule/Replay 不被 provider 配置污染。
- 用公共 receipt 让 CLI、HTTP、异步和 Console 读取同一状态，不复制传输层判断。

## C：Canonical plan 成功路径与脱敏 replay

- 为合法单组件和合法多组件计划建立最小脱敏 replay，验证结构规范化、DAG、TaskPlan、ToolRegistry、workflow 和 execution binding 的闭合。
- 已落地 `spatial-agent.canonical-plan-receipt.v1`，只有 accepted TaskPlan bridge 与 validated execution binding 同时成立时才标记 `executable`。
- 仅允许一次结构修复，比较 repair lineage 与最终 canonical receipt。
- 不用 replay 越过真实数据 readiness 或执行授权。

## D：可恢复交互与跨入口一致性

- 统一规划中、需要澄清、模型不可用、计划拒绝和执行失败的用户动作。
- 核对同步/异步/artifact/restart/Console 的状态和 evidence 合并规则，保持旧载荷安全降级。
- 前端仅增加结构化状态消费，不增加领域或工具名分支。

## E：Docker 阶段收口与一次显式 live

- 重建当前 Docker 镜像后集中运行 M305 契约、相邻回归、compileall、architecture strict、Node projection、Service smoke、生产 acceptance 和 readiness。
- 离线门禁全部通过后只执行一次 live；固定 deadline 与 0 重试，结果按 success、clarification 或 provider failure 如实记录。
- 已完成：Docker 精简门禁 **30/30**，compileall、architecture strict、Service smoke、Node projection、生产 acceptance 和 readiness **200**；唯一 live 形成合法单组件计划并完成 sync/async/artifact 对照。

## F：文档、版本和全局重规划

- 更新中文问题日志、milestones、恢复快照、任务账本、Spec/Plan 和测试策略引用。
- 阶段完成后提交并推送一个版本。
- 下一阶段继续按全局七维度规划，优先提升通用 Agent 能力，不陷入单一数据集调参。
- 已完成：中文问题记录、milestone、历史恢复卡、任务账本和 M306 全局能力图/Spec/Plan 已同步。

## 停止条件

如果 provider 或外部网络在一次显式 live 中超时，不重复发送；保留脱敏 receipt，完成离线成功路径、跨入口一致性和文档交付后继续全局重规划。
