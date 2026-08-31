# M335 能力地图：通用多工具执行与 Provider 健康

## 目标

从项目全局提升开放问题的可用率：让 Agent 能在受控能力目录内连续组合多个工具，识别模型/网络/数据失败原因，并把部分成功、证据缺口和下一步动作转成用户可理解的结果。GIS、经济、指标和文本只是能力提供方，不新增专题 Runtime 分支。

## 能力模块

| 模块 | 职责 | 依赖 | 交付边界 |
|---|---|---|---|
| `provider-health` | 统一模型、搜索和数据 Provider 的健康/延迟/失败分类 | RunBudget、Evidence | 安全 reason code、可重复诊断、无原文泄漏 |
| `react-composition` | 多工具连续决策、证据缺口判断、停止/澄清/降级 | ToolRegistry、Execution Policy | 一次一工具、schema/权限/预算门禁、有限循环 |
| `result-closure` | 多结果类型、来源 Bundle、范围/时间/单位对齐和部分成功 | Result Registry、Evidence Bundle | 结构化结果闭合，不隐式拼接 |
| `live-experience` | 阶段进度、超时反馈、答案流和失败恢复的统一投影 | RunEvent、SSE、Console | 跨入口一致，不暴露隐藏思维链 |
| `acceptance` | Docker、真实模型、受控网络和真实数据的最小纵向验收 | 以上模块 | 显式 live，不进入默认 CI |

## 构建顺序

`provider-health` → `react-composition` → `result-closure` → `live-experience` → `acceptance`

## 设计原则

- 先增强公共 Runtime seam，再由 Domain Pack 声明能力、数据和结果类型。
- Provider 健康只记录状态、耗时区间、尝试次数和 reason code，不保存模型原文、Prompt、网页正文或密钥。
- Agent 可以组合已注册能力，但不能绕过 ToolRegistry、schema、权限、网络策略、审批和预算。
- 默认测试保持离线精简；真实模型、Docker、GIS 和公共网络只作为显式验收路径。
