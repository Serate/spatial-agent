# M301 Planner-first 开放问题解析能力图

## 全局目标

在不重写 Runtime、ToolRegistry、生命周期和 Domain Pack 边界的前提下，消除“所有启用领域必须先补齐事实”造成的过早阻断。让 Planner 先看到有界、可解释的部分事实和候选能力，再由最终选中的组件决定是否需要补充字段。

M301 解决通用请求解析与状态语义，不新增 GIS 或 Economic 专题流程，也不引入 RAG、自由联网搜数或新的数据集。

## 能力切片

| 切片 | 要解决的问题 | 复用边界 | 交付证据 |
| --- | --- | --- | --- |
| request-fact-readiness | 区分完整、部分、缺失和不可用事实 | RequestFacts、Domain Pack requirements | 版本化 readiness 投影 |
| planner-first-discovery | 相关领域事实不足时仍允许能力发现和模型选择 | Capability Catalog、Planner envelope | 开放请求进入 Planner 的 contract |
| selected-component-gate | 只有被选中的组件才触发字段级阻断 | TaskPlan、component fact handoff、execution binding | 未满足事实不创建 execution run |
| clarification-continuation | 补充字段后只重建必要上下文并续跑 | continuation token、fingerprint、生命周期 | 首次澄清与补充后 identity 一致 |
| cross-entry-projection | CLI、HTTP、异步、artifact、View、Console 状态一致 | Result/View/Evidence 公共投影 | 状态和 next action 对照 |
| live-acceptance | 真实模型失败、澄清和成功可区分 | Docker、显式 live harness | 脱敏 receipt，不保存模型原文 |

## 七维度约束

- 产品：开放式问题先由 Agent 判断相关能力，用户只在确实缺少所选能力必需事实时补充。
- 架构：公共 Runtime 只处理 readiness 状态和契约，不判断领域词汇；Domain Pack 声明事实要求。
- 数据：部分事实不能伪造为 ready；数据集缺失、字段缺失和用户事实缺失分别保留原因。
- 模型：LLM 只能从 envelope 中选择已登记能力；Planner 可见“部分事实”，但不能据此绕过执行就绪门禁。
- 部署：默认 `openai + local` 不变；Rule/Replay 和离线测试不访问网络；Docker 是 Python/GIS 验证环境。
- 体验：用户看到“正在判断能力”“需要补充什么”或“模型服务暂不可用”，不看到内部字段、prompt 或思维链。
- 测试：以少量跨领域 contract 覆盖独立失败模式，阶段收口集中验证，不按每个小改动重复运行。

## 不在 M301 范围

- 不新增领域、数据源、RAG、联网搜索或 GIS 专用判断。
- 不把安全执行门禁降级为“模型说可以就执行”。
- 不为提高 live 成功率增加无界重试、放宽 schema 或保存 provider 原文。
