# Agent 当前恢复卡

这是新对话或上下文压缩后的唯一默认状态源。启动时只读本卡、Git 状态和最近提交；不要自动读取任务历史、问题日志、完整测试、模型响应或数据文件。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。当前切片为 **M220-B3：通用实体事实与上下文预算**。

## 当前进度

- Text Domain 已接入声明式 workflow catalog、组合 DAG、ToolRegistry/schema 校验、Result/View/Answer、HTTP、Artifact、Async 和 SQLite recovery。
- 公共 `component_evidence` 已接入 workflow selection，用于组件状态、覆盖、时效、来源、冲突和重验投影。
- `RequestFacts.entities` 已成为通用实体事实袋；能力发现、澄清和计划证据可消费任意 Domain 实体，`admin_name` 只保留为兼容别名。
- ContextBuilder 在预算不足时优先保留 workflow catalog/selection，先裁剪大型 advisory catalog，避免计划契约因上下文扩展而退化。
- M220-B3 当前实现待提交；具体版本号以 `git log -1 --oneline --decorate` 为准。
- Docker 容器 `ai-agent-spatial-agent-1` healthy；Python、compileall、阶段测试默认在 Docker 中执行。

## 阶段证据与下一步

- M220-B2 跨入口组件 evidence 回归 33/33；本切片扩展回归 66/66，Docker compileall 通过。
- 已验证非 GIS 自定义实体 `document_id` 可驱动 capability discovery 和 clarification，不需要 Runtime 增加领域字段。
- 下一步按全局能力矩阵进入 M220-B4：自动组合 workflow 的物化、真实模型 + GIS/Docker 端到端验收，以及前端动态结果展示与 replay/live 证据闭环。

## 不变量

- Runtime 负责生命周期、校验、恢复和 `allowed_actions`；Domain 只提供能力、数据和 advisory guidance。
- 新能力扩展 catalog、facts、schema、workflow、result/view，不增加区域或固定问句分支。
- 默认测试离线、精简；真实模型、真实 GIS、Docker、HTTP 和浏览器只在显式验收路径启用。
- 不提交 API key、`.env.production`、原始模型响应、真实 GIS 原始数据或私有路径。

## 读取预算

- 默认历史文件数：0；源码最多按需读 2 个文件；测试最多先读 1 个文件。
- 需要历史时先执行 `pwsh -NoProfile -File scripts/resume_context.ps1 -Topic "关键词" -MaxMatches 4 -ContextLines 8`，只读命中附近窗口。
- 当前卡超过约 3KB 时压缩旧证据，只保留目标、阶段、阻塞、下一步、最近验证和约束。
