# Agent 当前恢复快照（唯一短入口）

> 这是 Spatial Agent 的当前状态与恢复协议。新对话或上下文压缩后，先只阅读本文件；不要默认全文阅读历史交接文档。只有本文件列出的目标文件或通过 `rg` 定位到的历史问题需要按需读取。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。请求应经过 RequestFacts、能力发现、Planner、TaskPlan/DAG 校验、ToolRegistry、结果组合、结构化 Evidence 和可恢复生命周期；不得为单一区域或固定问句堆叠规则。

## 当前仓库状态

- 分支：`main`
- 恢复时以 `git log -1 --oneline` 和 `git status --short` 为准；本轮起始基线为 `15012ab feat: carry capability evidence into workflow selection`。
- 当前切片：M196-B.2 capability evidence 接管，以及本文件定义的精简恢复协议。
- 本切片涉及 `tests/test_m196_capability_evidence_provider.py`、阶段文档、中文问题日志和本短快照；这些变更应一起审计，不覆盖既有实现。

## M196-B.2 已完成内容

- HTTP `/runs`、SQLite 重启、Artifact、async 和 Service 的 capability evidence 保持 `spatial-agent.capability-evidence.v1` 一致。
- Provider 内部异常压缩为有界 `unavailable` evidence；原始异常、Provider payload、密钥和私有路径不得进入 plan evidence、Artifact 或 replay。
- M196-B.2 专项 10/10；M168/M140/M194/M195 受影响回归 26/26；Docker ci/stage/full-stage、compileall、production acceptance、HTTP runtime capability、Node/CDP 已有阶段证据通过。

## 下一阶段：M196-C

按全局七维度推进：

1. 候选能力、缺失事实、Evidence 和下一步动作进入通用澄清工作区。
2. 统一 selection、interaction、workspace、Artifact 的 evidence/action projection。
3. 由 Domain Pack 提供 status-to-action 建议，Runtime 只负责通用生命周期与安全门控。
4. 用脱敏 replay，必要时用 live-short，验证模型消费 evidence、补事实和有限 repair。
5. 覆盖 production FastAPI、async、SQLite restart、旧 Artifact 和静态资源 allowlist。
6. Text/GIS 共用动态 renderer；默认 quick/CI 保持精简。

## 测试与部署规则

- Python 测试、profile、compileall、GIS 和阶段回归默认在 Docker 容器 `ai-agent-spatial-agent-1` 内执行；宿主 Python 只能用于环境诊断。
- 重建当前代码后确认容器 healthy：

  `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --force-recreate`

- 默认使用精简 `quick`/`ci`/`stage`；完整历史测试、真实 GIS、真实模型、Docker、FastAPI 和浏览器属于显式验收路径。
- 不提交 `config/openai.local.json`、`.env.production`、API key、私有模型响应、原始 GIS 数据或仓库外 evidence。
- 阶段完成后更新本文件、`docs/milestones.md`、`docs/task-resume.md`，再提交并推送版本。

## 压缩恢复协议

1. 先读本文件，不全文读取 `agent-context-resume.md`、`task-resume.md` 或 `agent-development-issues.md`。
2. 检查 `git status --short --branch`、`git log -1 --oneline`，确认本文件中的提交和工作树描述是否仍准确。
3. 只读取“当前工作”列出的文件；需要历史问题时使用 `rg -n -i "关键词" docs/agent-development-issues.md`，再读取命中位置附近的有限行。
4. 先运行与当前改动直接相关的 Docker 专项测试；不要因为恢复上下文而自动运行完整历史矩阵。
5. 阶段状态发生变化时，先更新本文件，再把详细过程追加到历史档案。

## 历史档案索引

- `docs/agent-context-resume.md`：长期恢复与阶段历史，按需读取。
- `docs/task-resume.md`：任务规划与阶段验收历史，按需读取。
- `docs/milestones.md`：阶段完成记录，按需读取。
- `docs/agent-development-issues.md`：中文问题日志，先用 `rg` 定位，不全文扫描。
- `docs/agent-project-direction.md`：项目整体方向，需要进行全局重规划时读取。
