# Agent 当前恢复卡

这是新对话或上下文压缩后的唯一默认状态源。启动时只读本卡、Git 状态和最近提交；不要自动读取任务历史、问题日志、完整测试、模型响应或数据文件。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。当前切片为 **M220-B2：跨 Domain 组合能力与一致性**。

## 当前进度

- Text Domain 已接入声明式 workflow catalog、组合 DAG、ToolRegistry/schema 校验、Result/View/Answer、HTTP、Artifact、Async 和 SQLite recovery。
- 公共 `component_evidence` 已接入 workflow selection，用于组件状态、覆盖、时效、来源、冲突和重验投影。
- M220-B2 已完成实现，当前工作树包含待提交的 Text/证据/组合测试改动；具体版本号以 `git log -1 --oneline --decorate` 为准。
- Docker 容器 `ai-agent-spatial-agent-1` healthy；Python、compileall、阶段测试默认在 Docker 中执行。

## 阶段证据与下一步

- HTTP、detail、sync artifact、async、recovered、async artifact 的组件 evidence 已统一；M158/M194/M195/M220 精简回归 33/33，Docker compileall 通过。
- 已修复 GIS 自动复合能力缺少稳定 component identity 导致 HTTP 首次结果丢失 Registry entry 的问题；Runtime 不新增 GIS 分支。
- 下一步按全局能力矩阵重规划 M220-B3，优先评估跨 Domain 动态组合发现、真实数据/模型验收与 replay/live 证据闭环。

## 不变量

- Runtime 负责生命周期、校验、恢复和 `allowed_actions`；Domain 只提供能力、数据和 advisory guidance。
- 新能力扩展 catalog、facts、schema、workflow、result/view，不增加区域或固定问句分支。
- 默认测试离线、精简；真实模型、真实 GIS、Docker、HTTP 和浏览器只在显式验收路径启用。
- 不提交 API key、`.env.production`、原始模型响应、真实 GIS 原始数据或私有路径。

## 读取预算

- 默认历史文件数：0；源码最多按需读 2 个文件；测试最多先读 1 个文件。
- 需要历史时先执行 `pwsh -NoProfile -File scripts/resume_context.ps1 -Topic "关键词" -MaxMatches 4 -ContextLines 8`，只读命中附近窗口。
- 当前卡超过约 3KB 时压缩旧证据，只保留目标、阶段、阻塞、下一步、最近验证和约束。
