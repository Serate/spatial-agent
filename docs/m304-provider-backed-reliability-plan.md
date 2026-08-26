# M304 Provider-backed 规划可靠性与可恢复交互实施计划

## A：全局状态矩阵与入口基线

- 对照 CLI、FastAPI、stdlib HTTP、async、artifact/restart 和 Console 的规划状态投影。
- 冻结 provider success、timeout、clarification、rejection、execution failure 的 reason/error/failure plane 映射。
- 只保留必要源码和精简 fixture，明确不读取模型原文和密钥。

## B：Provider 健康与 deadline 公共 seam

- 审查现有 OpenAI-compatible config、structured-output profile、deadline harness 和 provider evidence。
- 统一配置缺失、网络不可达、超时、响应非法和重试耗尽的可观测 receipt。
- 确保产品默认 `openai + local`，离线 Rule/Replay 不被 provider 配置污染。

## C：真实模型规划成功路径

- 以阶段化 selection Envelope 和能力 readiness 为唯一模型输入边界。
- 通过现有 canonical adapter、TaskPlan/DAG、ToolRegistry 和 execution binding 验证合法计划。
- 仅保留一次有界 repair；建立脱敏 replay fixture，避免用重复 live 代替契约测试。

## D：跨入口可恢复交互

- 统一活动规划、用户澄清、provider 失败、可重试动作和最终执行状态。
- Console 只按结构化 evidence 动态展示，不新增 GIS/Economic 页面分支或技术标签。
- 保证同步响应、异步轮询、artifact 和重启恢复的状态/证据一致。

## E：Docker 阶段收口

- 集中运行本阶段契约、相邻回归、compileall、architecture strict、Node projection、Service smoke 和 readiness。
- readiness 通过且离线门禁全绿后，显式执行一次真实模型验收；不重复调用，不因 timeout 自动增加预算或重试。
- 比较 live receipt 与离线 Replay 的状态结构，不要求 provider 不稳定时伪造成功。

## F：文档、版本和全局重规划

- 更新中文问题日志、milestones、恢复快照、任务账本和本阶段 Plan。
- 阶段完成后提交并推送一个版本。
- 从产品、架构、数据、模型、部署、体验、测试七维度重规划下一阶段；优先通用能力，不陷入数据细节。

## 依赖与停止条件

顺序为 `A → B → C → D → E → F`，当前串行执行。开发期间只做必要静态检查，阶段末集中测试一次。若 provider、Docker 或外部网络连续阻塞，保留结构化 receipt 并停止 live 重试，转而完成可离线验证和文档交付。
