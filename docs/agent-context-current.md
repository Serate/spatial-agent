# Agent 当前恢复卡

这是新对话或上下文压缩后的唯一默认状态源。启动时只读本卡、Git 状态和最近提交；不要自动读取任务历史、问题日志、完整测试、模型响应或数据文件。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。当前切片为 **M220-B4：Domain-owned 自动 workflow 物化**。

## 当前进度

- Text Domain 已接入声明式 workflow catalog、组合 DAG、ToolRegistry/schema 校验、Result/View/Answer、HTTP、Artifact、Async 和 SQLite recovery。
- Text Domain 的自然语言请求现在可提取多个任务，Domain 自动物化组合组件，planner 通过公共 workflow selection 编译多步骤 DAG；单任务和显式 workflow 保持兼容。
- 公共 `component_evidence` 已接入 workflow selection，用于组件状态、覆盖、时效、来源、冲突和重验投影。
- `RequestFacts.entities` 已成为通用实体事实袋；能力发现、澄清和计划证据可消费任意 Domain 实体，`admin_name` 只保留为兼容别名。
- ContextBuilder 在预算不足时优先保留 workflow catalog/selection，先裁剪大型 advisory catalog，避免计划契约因上下文扩展而退化。
- M220-B3 已提交为 `2811446`；M220-B4 当前实现待提交，具体版本号以 `git log -1 --oneline --decorate` 为准。
- Docker 容器 `ai-agent-spatial-agent-1` healthy；Python、compileall、阶段测试默认在 Docker 中执行。

## 阶段证据与下一步

- M220-B4 Text Domain 回归 10/10；与 M194/M195/M220 公共组合、evidence、跨 Domain seam 的精简回归 31/31，Docker compileall 通过。
- 已验证非 GIS 自定义实体 `document_id` 可驱动 capability discovery 和 clarification，不需要 Runtime 增加领域字段。
- 下一步按全局能力矩阵：验证自动组合 workflow 的真实模型路径、GIS/Docker 端到端路径和前端动态结果展示；随后补齐 replay/live evidence 闭环。

## 不变量

- Runtime 负责生命周期、校验、恢复和 `allowed_actions`；Domain 只提供能力、数据和 advisory guidance。
- 新能力扩展 catalog、facts、schema、workflow、result/view，不增加区域或固定问句分支。
- 默认测试离线、精简；真实模型、真实 GIS、Docker、HTTP 和浏览器只在显式验收路径启用。
- 不提交 API key、`.env.production`、原始模型响应、真实 GIS 原始数据或私有路径。

## 读取预算

- 默认历史文件数：0；源码最多按需读 2 个文件；测试最多先读 1 个文件。
- 需要历史时先执行 `pwsh -NoProfile -File scripts/resume_context.ps1 -Topic "关键词" -MaxMatches 4 -ContextLines 8`，只读命中附近窗口。
- 当前卡超过约 2KB 时压缩旧证据，只保留目标、阶段、阻塞、下一步、最近验证和约束。
