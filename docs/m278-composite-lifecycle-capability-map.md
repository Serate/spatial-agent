# Capability Map: M278 Composite 可恢复生命周期

| 模块 ID | 责任 | 依赖 |
|---|---|---|
| composite-envelope | 让 Composite Result 作为公共 Result Contract 进入 AgentRunResult、SQLite 和 artifact | M275 contract |
| composite-run-lifecycle | 通过现有 AsyncApplication 提供同步持久化、异步提交、幂等、取消、轮询和重启接管 | composite-envelope、M276 coordinator |
| composite-http-recovery | 将 submit、observability、run detail 和 evidence 接入共享 HTTPApplication | composite-run-lifecycle、M256 HTTP seam |

构建顺序：`composite-envelope → composite-run-lifecycle → composite-http-recovery`。

本阶段不新增 GIS/Economic 工具，不让 Domain Service 互相持有，不在 HTTP transport 中复制组件循环。前端动态 Composite View 和真实 LLM 自动生成跨域计划留到后续全局阶段。
