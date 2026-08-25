# M283 开放式请求 Agent 闭环能力图

## 阶段目标

在 M282 的 Request Context 与 Planner Gateway 之上，打通一条用户可感知、可验收的开放式请求闭环：

```text
自然语言请求 → RequestFacts/能力发现 → Rule/Replay/LLM Planner
→ canonical Composite Plan → 受控执行 → Answer/View/Evidence
```

重点是让 Agent 的架构能力传导到体验和真实验收，不新增针对某个地区、专题、数据集或固定问句的流程。

## 能力分层

| 模块 | 责任 | 依赖 | 不负责 |
|---|---|---|---|
| `open-query-entry` | 接收请求、选择领域、构建 v2 context | Domain Host、Context Builder | 解析私有数据或创建工具 |
| `planner-gateway` | 让 Rule/Replay/LLM 产生同一 canonical plan | context、Planner schema、allowlist | 执行工具、猜测缺失事实 |
| `provider-compatibility` | 对文档化的中转字段漂移做有界归一化 | provider adapter、replay | 接受任意未知字段 |
| `execution-bridge` | 将合法计划交给既有 Composite lifecycle | M278/M281 | 复制 Runtime/ToolRegistry 生命周期 |
| `result-experience` | 将状态、答案、View、Evidence 变成用户可读阶段 | Result/View/Evidence | 暴露思维链或原始模型响应 |
| `live-acceptance` | 验证真实模型、真实 GIS、Docker 和跨入口一致性 | Docker、HTTP、artifact、browser | 进入默认 CI 或保存密钥 |

## 七维度全局依据

1. 产品：用户看到“发现能力 → 检查数据 → 生成计划 → 执行 → 汇总”，而不只是工具日志。
2. 架构：复用 M282/M278/M281 公共边界，不把开放请求逻辑复制到 transport 或 Domain。
3. 数据：模型只能选择已登记且健康检查通过的数据；缺失数据进入澄清或可恢复不可用状态。
4. 模型：Provider readiness、上下文合法、计划 schema 合法和执行成功分开验收；不因一次 live 失败放宽 allowlist。
5. 部署：Docker 是 Python/GIS/HTTP 验收环境；默认 CI 继续离线精简。
6. 体验：前端动态消费 context、plan、answer、view、evidence，突出结论和下一步，详情可展开。
7. 测试：fake/replay 锁定确定性行为，真实模型/GIS/browser 作为显式短验收矩阵。

## 依赖顺序

`planner-gateway` → `open-query-success` → `result-experience` → `cross-entry-live` → `global-replan`

## 边界

- Always：先构建有界 context；计划经过 schema、Domain/Capability allowlist 和生命周期 gate。
- Ask first：新增公共 schema、改变默认 Planner、增加依赖或改变前端主结果模型。
- Never：新增固定问句分支、模型自由搜索/下载数据、保存 prompt/原文/密钥、用前端分支掩盖后端状态。
