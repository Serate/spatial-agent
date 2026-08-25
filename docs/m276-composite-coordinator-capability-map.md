# M276 能力图：Composite Coordinator 第一条执行切片

## 目标

让已经规范化的 Composite request 能够在一个 transport-neutral application seam 中按组件 DAG 串行执行。每个组件必须通过 `DomainRuntimeHost` 的 allowlist 获取对应 Domain Service，并复用该 Service 原有 Runtime、Planner、ToolRegistry、生命周期和 Result Contract。

## 能力边界

| 模块 ID | 职责 | 依赖 |
|---|---|---|
| `composite-coordinator` | 接收规范化 Composite request，管理组件状态和执行顺序 | M275 `composite-request`、`DomainRuntimeHost` |
| `composite-dependency-gate` | 在执行前传播缺失/失败/阻塞依赖，不执行不可满足的组件 | `composite-coordinator` |
| `composite-result-assembly` | 将各组件公共结果交给 M275 Result/Evidence 聚合器 | M275 `composite-result`、`composite-evidence` |

## 构建顺序

`composite-coordinator` → `composite-dependency-gate` → `composite-result-assembly`

## 非目标

- 本阶段不实现新的 LLM Composite Planner；输入先要求组件 Domain/请求已经明确。
- 不并行执行组件；当前 goal 的最大并发度为 1，且串行更容易保持依赖和失败语义确定。
- 不新增 HTTP、async worker、SQLite/artifact 持久化入口；后续 transport 只调用本阶段 application seam。
- 不把 GIS/Economic 名称写入公共 coordinator。
