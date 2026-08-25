# M275 能力图：领域中立 Composite 编排接缝

## 目标

为一次需要多个已注册 Domain/能力的逻辑请求建立公共边界，使 GIS、Economic 和未来 Domain 能共享同一组请求、结果、证据和 View 契约。M275 先稳定契约，不把跨域语义写进 Runtime。

## 能力边界

| 模块 ID | 职责 | 依赖 |
|---|---|---|
| `composite-request` | 规范化组件、Domain 身份、依赖关系和有界请求输入 | Domain Catalog（只做后续执行时校验） |
| `composite-result` | 聚合多个子结果的数据形态、状态、回答摘要和结构化 View | `composite-request` |
| `composite-evidence` | 聚合子结果的来源、降级、失败、artifact 引用和证据索引 | `composite-result` |
| `composite-entry` | 为未来的 Host/HTTP/async/artifact 编排提供单一投影入口 | `composite-request`、`composite-result`、`composite-evidence` |

## 构建顺序

`composite-request` → `composite-result` → `composite-evidence` → `composite-entry`
## 本阶段不纳入

- 不在公共 Runtime 中增加 GIS 或 Economic 专用分支。
- 不让模型直接决定未注册的 Domain、工具、数据集或路径。
- 不在 live harness 中偷偷拼接两个独立 Runtime。
- 不把模型原文或内部思维过程放进 Composite 结果。
