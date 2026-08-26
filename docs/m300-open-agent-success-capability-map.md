# M300 开放问题 Agent 成功率与答案体验能力图

## 目标

从项目整体提升默认 Agent 对开放式地理问题的处理能力，让用户感受到“提出问题 → Agent 自主发现可用能力 → 形成受控计划 → 执行并总结”，同时保持 Runtime、ToolRegistry、Domain Pack 和安全门禁稳定。

## 能力边界

| 模块 | 职责 | 依赖 |
|---|---|---|
| `open-question-understanding` | 将自然语言映射为有界 RequestFacts、缺失事实和分析目标 | 现有 RequestFacts、Domain Pack |
| `capability-composition` | 从目录选择并组合已注册能力，生成可物化 TaskPlan | Capability Catalog、Workflow、ToolRegistry |
| `provider-reliability` | 处理真实模型超时、结构化输出失败和有限恢复 | Planner envelope、生命周期 |
| `answer-experience` | 将 Result/View/Evidence 组合成简洁、可信、可读的用户答案 | Result、Evidence、前端 projection |
| `acceptance-observability` | 用少量代表性样本比较默认产品、规则回放和真实模型路径 | Docker、HTTP、Artifact、Trace |

## 构建顺序

`open-question-understanding` → `capability-composition` → `provider-reliability` → `answer-experience` → `acceptance-observability`

所有模块共享现有 Runtime 生命周期；不得为单一区域、单一专题或固定问句新增流程分支。
