# M269 能力地图：通用记录分析

## 目标

把“对结构化记录做筛选、聚合、时间序列和比较”的重复逻辑收敛为一个领域中立深模块。GIS、Economic 和 Indicators 只负责数据读取、字段/来源校验、领域目录和工具适配，不复制分析语义。

## 模块边界

| 模块 ID | 职责 | 依赖 |
|---|---|---|
| `record-analysis-core` | 对已规范化记录执行有界 filter、aggregate、timeseries、compare，并返回版本化中间结果 | `data_kinds` |
| `record-analysis-contract` | 记录分析请求、条件、聚合函数、状态码和结果字段的公共契约 | `record-analysis-core` |
| `record-analysis-adapters` | GIS 文件型矢量、Economic/Indicators 指标 Provider 将数据接入核心；保留领域来源与字段校验 | `record-analysis-core`, `record-analysis-contract`, `ToolRegistry` |
| `record-analysis-acceptance` | 通过 Docker 验证真实经济记录与真实地震记录共享核心、Result/View/Evidence 和恢复语义 | 三个前置模块 |

## 构建顺序

`record-analysis-core` → `record-analysis-contract` → `record-analysis-adapters` → `record-analysis-acceptance`

## 非目标

- 不重写 Agent Runtime、Planner、ToolRegistry 或生命周期。
- 不引入 RAG、MCP、网络搜索或自动下载。
- 不让核心模块读取文件、访问网络、识别 GIS/经济领域词汇或依赖具体数据集名称。
- 不删除 Economic/Indicators 的既有工具；先用兼容适配证明复用，再逐步收敛重复入口。
