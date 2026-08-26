# M299 默认 Agent 成功路径实施计划

## A：全局基线与预算冻结

- 盘点当前 Context Builder、Planner、provider wire payload、selection evidence 和恢复载荷的预算。
- 固定 success、clarification、data unavailable、provider failure 四类验收矩阵与 identity 字段。
- 只做静态审计和最小 contract 设计，不重复运行完整测试。

## B：分层 Planner context

- 新增领域中立的紧凑投影 seam：能力索引保留 identity、data profile、requirements 和 readiness；选中候选再保留有限 workflow/执行闭合信息。
- Context Builder、LLM Planner 和 provider payload 共享一个版本化预算；超限保持 fail closed 并提供恢复动作。
- Rule/Replay/LLM 继续消费同一 canonical context，不复制领域策略。

## C：选择与澄清 evidence

- 统一请求事实、候选能力、选中能力、不可用原因和 next actions 的安全摘要。
- 复用已有 discovery、repair、TaskPlan 和 execution binding；不新增 repair 回合，不让模型改变权限或数据选择。
- 覆盖未知能力、缺失事实、数据未就绪和结构化输出不合规四类差异。

## D：阶段体验与跨入口恢复

- Console 从结构化状态投影阶段条与用户文案，详细 evidence 继续渐进展开。
- 检查同步/异步轮询、artifact、SQLite/restart 和 HTTP 的阶段/selection identity 不丢失。
- 保持前端领域中立，不按工具名、区域或专题增加分支。

## E：真实验收与交付

- Docker 真实数据执行一次 Replay/Rule 对照，验证已准备计划的同步/异步、artifact/restart 核心 identity。
- 配置可用时执行一次显式 live，记录 provider 可达、澄清或安全失败，不保存模型原文。
- 集中运行 M299 与相邻 compact contract、compileall、architecture strict、Node smoke、readiness；更新中文问题日志、恢复账本、milestone，提交推送。

## F：全局重规划

- 从产品、架构、数据、模型、部署、体验和测试七个维度评估默认 Agent 成功率与剩余缺口。
- 下一阶段优先解决全局瓶颈，不因单一 live 问句增加专用流程。

## 阶段收口记录

- A～D 已完成：Planner envelope、selection evidence、阶段投影、同步/异步/恢复和 artifact 证据已贯通。
- E 已完成：Docker 真实 Economic local 数据与 Replay/Rule 对照通过；显式中转 live 为 provider timeout，按安全失败记录，未创建执行 run。
- F 已完成：精简门禁通过，中文问题日志、任务账本、milestone 和恢复快照已更新；下一阶段为 M300，规划文件见 `docs/m300-open-agent-success-*`。
