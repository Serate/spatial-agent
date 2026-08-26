# M308 开放式多组件纵向链路能力图

## 目标

从项目整体目标验证 Agent 的“自主组合”和“用户可读答案”是否真正贯通：让一个开放式请求可以从能力发现开始，动态选择三个或更多已登记能力，形成合法 DAG，执行混合数据类型，最后把结构化事实转换为简洁答案、限制、视图和证据。GIS 与 Economic 只是现有 Domain Pack，不在本阶段增加专题分支。

## 能力模块

| 模块 ID | 责任 | 依赖 |
|---|---|---|
| open-composition-scenarios | 建立领域中立的 3+ 组件请求/计划/执行验收矩阵，覆盖澄清、拒绝、成功和部分失败 | — |
| result-to-answer | 让答案生成只消费结构化 Result/Evidence，输出非技术用户可读的结论、限制和下一步；模型不可用时安全降级 | open-composition-scenarios |
| cross-entry-evidence | 对照同步、异步、HTTP、Console、artifact 和重启恢复的结果、View、Evidence 与 identity | open-composition-scenarios, result-to-answer |
| acceptance-and-release | Docker 阶段门禁、必要的一次 live、文档和版本交付 | open-composition-scenarios, result-to-answer, cross-entry-evidence |

## 构建顺序

`open-composition-scenarios → result-to-answer → cross-entry-evidence → acceptance-and-release`

## 不在本阶段

- 不增加 GIS/Economic 或其它领域工具，不为固定区域或问句增加分支。
- 不引入 RAG、联网搜索或自由下载；模型只能选择已登记且通过 readiness/schema 门禁的能力。
- 不暴露模型原文、prompt、内部思维链、密钥、完整原始数据或私有路径。
