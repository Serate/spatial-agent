# M295 全局开放式分析与数据发现能力图

## 阶段定位

M294 已经把“已验证计划 → 实际执行 → 结果/答案/证据”闭合。M295 不再局部修补某个 GIS 工具，而是从项目整体推进下一条主线：让 Agent 面对未预先写成固定问句的跨领域问题时，能够先发现需要什么能力与数据，再进行有界规划。

GIS 和 Economic 仍是业务载体；公共 Runtime、ToolRegistry、TaskPlan/DAG、execution binding 和生命周期不增加领域分支。

## 七维度盘点

### 产品

- 用户可以直接提出开放式空间问题，不需要知道工具名称或数据集名称。
- 系统能够区分“能力不存在”“能力存在但缺数据”“事实不完整”和“计划不可执行”，并给出下一步动作。
- 结果先呈现结论和关键发现，数据来源、计划和证据作为渐进详情。

### 架构

- 将请求理解、能力匹配、数据需求、数据发现和计划选择定义为领域中立边界。
- 不复制 Planner 或 Runtime；所有候选能力最终仍进入 TaskPlan/completeness/execution-binding 门禁。
- 允许 Domain Pack 提供目录、事实提取和数据 readiness，公共层只协调结构化结果。

### 数据与 GIS

- 统一表达数据集身份、覆盖范围、时间范围、CRS/分辨率、来源和 readiness。
- 数据缺失、字段不匹配、时间范围不足或后端不可用时，保留可恢复事实和证据。
- 真实武汉数据只作为验收载荷，不把数据文件名、洪山区或固定指标写入公共流程。

### 模型工程

- LLM Planner 只从能力目录和数据发现结果中选择已注册能力。
- Rule/Replay/LLM 共享同一 RequestFacts、capability match、clarification 和 TaskPlan 契约。
- Provider 输出失败只能触发有限 repair/clarification/fallback，不能扩大工具权限。

### 部署与恢复

- Docker 是 Python/GIS/compile/架构/readiness 的默认执行环境。
- discovery receipt、clarification continuation、execution binding 和 artifact/restart 使用同一 request identity。
- 默认运行离线精简；真实模型、真实 GIS 和 HTTP 只在阶段收口显式验收。

### 体验

- 前端消费 `Result/View/Evidence`，动态展示指标、矢量、栅格、时间序列和来源。
- 用户看不到内部 prompt、完整模型原文、工具参数或私有路径。
- 同一开放问题在澄清、执行中、部分完成和失败时都有明确可读状态。

### 测试与交付

- 一个完整阶段包覆盖契约、实现、跨入口集成、Docker/显式 live、文档和推送。
- 只保留有独立失败模式的 compact contract；阶段收口统一执行，不因任务数量增加而复制测试轮次。

## M295 目标闭环

```text
开放请求 -> RequestFacts -> 能力/数据需求 -> 有界发现与 readiness
-> 澄清或 TaskPlan/DAG -> execution binding -> Result/View/Evidence
-> CLI/HTTP/前端/artifact/restart 一致 -> 全局复盘
```

## 不在本阶段

- 不引入 RAG、知识库问答或新的外部数据抓取平台。
- 不为经济分析添加固定“GDP/最近发展”专用流程。
- 不新增大量 GIS 算子；若缺能力，先记录为 catalog 的结构化缺口。
- 不替换 Runtime、ToolRegistry、生命周期或 execution binding。
