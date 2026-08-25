# M277 能力图：Composite HTTP 统一入口

## 目标

把 M276 Coordinator 接入已有 `HTTPApplication`，让 FastAPI 与 stdlib HTTP server 通过同一个语义命令执行同步 Composite 请求。传输层只增加路由解析、JSON 读取和异常状态映射，不复制组件循环。

## 能力边界

| 模块 ID | 职责 | 依赖 |
|---|---|---|
| `composite-http-command` | 在 HTTPApplication 中分发 `composite_run` | M276 `CompositeApplication` |
| `composite-http-route` | FastAPI/stdlib 暴露同语义 `/composite-runs` | `composite-http-command` |
| `composite-http-contract` | 验证两入口返回同一 Result/Evidence 形状和错误码 | M275/M276、HTTP transport |

## 构建顺序

`composite-http-command` → `composite-http-route` → `composite-http-contract`

## 非目标

- 不在本阶段接入 async worker、SQLite/artifact/restart。
- 不在传输层解析 Domain、能力、工具或自然语言。
- 不增加前端专用 Composite 分支；前端后续消费统一 Result/View。
