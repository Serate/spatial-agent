# M305 Provider-backed 成功率与可恢复交互能力图

## 背景

M304 已把 provider 配置健康、structured-output 能力、deadline、失败类别和 Console 状态投影收敛到公共 seam。当前真实模型唯一验收仍可能因中转延迟超时，因此下一阶段要提升“请求能够在有限预算内形成合法计划”的成功率，同时保持失败可解释、可恢复和不重复消耗 token。

## 全局能力切片

| 维度 | M305 目标 | 交付边界 |
| --- | --- | --- |
| 产品 | 用户能看到规划进度、失败原因和明确的重试/检查配置动作 | 不显示 prompt、模型原文、内部指纹 |
| 架构 | provider 请求预算、阶段 Envelope、canonical 计划适配和生命周期继续单源 | 不绕过 TaskPlan、ToolRegistry、workflow 或 execution binding |
| 数据 | 只把当前请求所需的最小事实、就绪状态和能力索引交给模型 | 不绑定某个区域、专题或数据文件 |
| 模型 | 在有限上下文和输出预算内更稳定地产生可校验 Composite 计划 | 只允许已登记能力；最多一次结构修复 |
| 部署 | 配置、网络、超时和 structured-output 能力可诊断 | 不把密钥或中转地址写入代码/文档 |
| 体验 | provider 失败、澄清、拒绝和执行失败在所有入口一致 | 前端只消费结构化 Result/View/Evidence |
| 测试 | 用脱敏 replay 覆盖成功路径，用一次 live 观察真实 provider | 默认 CI 离线、精简、可重复 |

## 能力依赖

`provider-runtime → request-budget → canonical-plan-replay → recovery-projection → docker/live-acceptance`

## 明确不做

- 不新增 RAG、专题知识库或固定问句分支。
- 不用无界 token、无界重试或自动切换模型掩盖 provider 失败。
- 不把模型输出直接变成执行授权，所有计划继续经过既有 canonical DAG、TaskPlan、ToolRegistry 和 binding 门禁。
- 不以一次 live 成功或失败代表整体系统成功率；live 只提供显式环境证据。
