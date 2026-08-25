# Spec: M281 动态 Composite 结果体验与跨入口一致性

## Objective

让 Agent 的运行证据以用户能理解的方式呈现。系统从 canonical Composite Result 生成领域中立的答案与 View Projection，所有入口共享同一结构化核心；前端不再依赖 GIS 专用页面分支或固定工具名。

## Required

1. 新增版本化、受限的 `spatial-agent.composite-view.v1` 投影，至少包含 `answer`、`sections`、`views`、`evidence`、`artifacts`、`status` 和 request fingerprint。
2. `answer` 至少支持 headline、summary、key findings、limitations；默认简洁，详细执行轨迹和证据可展开。
3. View 根据 `data_profile`/View contract 映射到 vector map/table、raster extent/statistics、metrics cards/table、timeseries chart、document evidence/source list；Composite 只负责分组和排序。
4. 失败、澄清、partial、数据缺失和截断必须生成结构化状态与用户可读说明；不能把错误堆栈或模型原文直接交给前端。
5. HTTP、CLI、artifact 和前端消费同一投影；同一 request fingerprint 的核心 status、answer、View IDs 和 evidence references 一致。
6. 前端初始空态、加载态、成功态、partial/error/clarification 态均可用；地图/图表组件没有领域名称判断。
7. 真实模型仍是显式验收路径；答案生成失败时使用 canonical facts 的安全 fallback，不阻塞结果展示。

## Non-functional

- 不修改既有 `spatial-agent.composite-request.v1`、`composite_result`、M278 lifecycle 版本。
- 投影有大小、文本、View 数量、要素和证据引用预算；敏感字段、路径、prompt、模型原文和密钥 fail closed。
- 默认测试离线精简；Docker/browser/live 只显式执行。
- 不为了一个地区、数据集、问题表达或领域增加前端/Runtime 专用分支。

## Acceptance

- fake Composite 覆盖 vector+raster+metrics+timeseries 混合结果、partial、澄清、失败和 artifact 引用。
- CLI 与 HTTP 对同一 canonical result 产生一致的 projection fingerprint、answer 摘要和 View IDs。
- Docker 生产镜像 browser smoke 验证空态 → 提交 → 结果渲染 → 展开 evidence；不要求默认 CI 联网。
- 至少一条真实 GIS + Economic Composite 使用同一 projection；真实模型失败时仍显示结构化失败/降级说明。
- architecture strict、compileall、精简 contract、HTTP contract 和 browser smoke 通过。

## Deferred

- RAG、外部搜索、实时数据抓取和自动新增工具。
- 完整移动端布局和复杂地图编辑器。
- 模型思维链展示；只展示结构化阶段、计划摘要和 evidence。
