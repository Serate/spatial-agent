# M304 Provider-backed 规划可靠性与可恢复交互能力图

## 背景

M303 已证明 Runtime、Composite canonical DAG、真实 GIS/Economic 执行、异步恢复和结构化结果链路可以闭合；但唯一一次真实模型验收在中转链路超时。当前缺口不是继续增加 GIS 工具，而是让 provider-backed Agent 的规划状态、失败边界和用户动作在各入口一致可用。

## 全局能力切片

| 维度 | M304 目标 | 交付边界 |
| --- | --- | --- |
| 产品 | 用户能区分“正在规划、需要补充、模型暂不可用、计划被拒绝、执行失败” | 统一状态与下一步动作，不暴露内部 prompt/思维链 |
| 架构 | provider 调用、deadline、structured capability、failure receipt 只有一个公共语义 | 不复制 Runtime 生命周期，不绕过 canonical DAG、TaskPlan 或 binding |
| 数据 | 规划只看到有界 readiness、能力索引和必要事实缺口 | 不为单一区域、专题或数据文件增加分支 |
| 模型 | 在有限预算内更稳定地产生可校验的 Composite 计划 | 只允许已登记能力；最多一次有界 repair；失败保持 fail closed |
| 部署 | Docker、HTTP readiness 和配置健康能说明 provider 是否可调用 | 中转地址、超时和密钥只由部署配置提供，不写入仓库 |
| 体验 | sync/async/Console 显示同一阶段进度和可恢复动作 | 前端只消费结构化 Result/Evidence/View |
| 测试 | 离线 fixture 覆盖状态矩阵，阶段收口只做一次 live | Docker 是 Python/GIS 统一执行面，live 不进入默认 CI |

## 能力依赖

`provider-health/deadline → structured-plan-delivery → lifecycle-projection → docker/live-acceptance`

## 明确不做

- 不新增 RAG、专题知识库或单一问句分支。
- 不将 provider timeout 转换成用户事实澄清或伪造成功计划。
- 不增加无界重试，不保存模型原文、完整 prompt、密钥或私有原始数据。
- 不因 live 不稳定而删除真实模型验收；用脱敏 receipt 保留可复现结论。
