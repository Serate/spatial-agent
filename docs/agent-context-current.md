# Agent 当前恢复快照（唯一短入口）

> 这是 Spatial Agent 的当前状态与恢复协议。新对话或上下文压缩后，先只阅读本文件；不要默认全文阅读历史交接文档或当前工作集。工作集只是有序索引，不是一次性阅读清单；代码必须按 seam 分批读取。

## 压缩恢复触发规则

当出现“上下文已压缩”“继续之前的工作”、新对话接续，或当前上下文只提供摘要时，立即把本文件作为唯一恢复入口。恢复阶段只做以下动作：

1. 读取本文件，获取当前目标、切片、工作集和验证边界。
2. 用 `git status --short --branch`、`git log -1 --oneline` 核对仓库事实；仓库现状优先于过期快照。
3. 只读取“当前工作集”中的文件；历史文档必须先用 `rg -n -i "关键词" <文件>` 定位，再读取命中行附近的有限范围。
4. 先执行当前切片的最小 Docker 专项检查，确认后再修改代码；不要因恢复而自动加载或运行完整历史矩阵。
5. 完成一个可验证的小阶段后，先更新本文件的状态，再更新详细历史文档。

本文件只保存“现在继续工作所必需的信息”，不记录完整日志、长测试输出、原始模型响应或大段代码；目标是让压缩恢复稳定且低 token。若本文件与代码、测试或最新提交冲突，以代码和可复现验证结果为准，并在继续开发前修正本快照。

## 文件读取预算

- 恢复首轮只允许读取本文件、`git status --short --branch` 和 `git log -1 --oneline`；不要在首轮打开源码、历史文档或完整测试文件。
- 代码侦察先用 `rg -n "符号|schema|入口" 目标文件` 获取定位；随后只读取命中行附近的范围，不使用 `Get-Content -Raw` 批量加载模块。
- 单个工作回合默认最多读取 3 个源码文件和 1 个直接相关测试文件；先完成一个 seam，再决定是否扩展到下一个 seam。
- 当前工作集按“先读 / 后读 / 集成时才读”分层；未到对应实现步骤的文件保持不读。若确实需要超过预算，先在快照中写明新增 seam、原因和精确文件，再继续。
- 测试优先选择一个专项或 contract 入口；只有专项通过且需要证明跨入口一致性时，才读取或运行下一层测试。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。请求应经过 RequestFacts、能力发现、Planner、TaskPlan/DAG 校验、ToolRegistry、结果组合、结构化 Evidence 和可恢复生命周期；不得为单一区域或固定问句堆叠规则。

## 当前仓库状态

- 分支：`main`
- 恢复时以 `git log -1 --oneline` 和 `git status --short` 为准；不要把快照中的历史提交号当作当前基线。
- 当前切片：M196-C evidence/action projection 与开放式澄清工作区。
- M196-C.1 已完成 `workflow_selection` / `selection_interaction` 的 evidence/action guidance 公共 seam、Domain 适配器和 Runtime 单次 context 注入；Docker 专项与旧交互回归 13/13 通过。
- M196-C.2 已让 Text/GIS Domain 提供同一 guidance contract；M196-C 专项 14/14、M196 capability evidence contract 10/10 通过，容器 healthy。
- M196-C.3 已让 Result Contract 在 `planning.workflow_selection` 与 `selection_interaction` 复用同一 guidance normalizer；新增 contract 与相关回归合计 25/25 通过。

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

## 当前工作集（按读取顺序）

1. **已完成**：`agent/workflow_selection.py`、`agent/selection_interaction.py`、`agent/domain_contract.py`、`agent/runtime.py`、`domains/text/domain.py`、`domains/gis/domain.py`、`result_contract.py`；已验证 planning/interaction 同一 guidance projection。
2. **下一首读**：`agent/service_async.py` 中 `build_async_result_evidence` / `normalize_async_result_evidence`；只验证 async projection 是否保留 guidance。
3. **随后才读**：`agent/artifact_store.py`、`serve_api.py`、`production_api.py` 和 `web/console_*.js`；按跨入口 equality 逐个接入，不要一次性打开。
4. **按需验证**：优先一个 `tests/test_m196_*.py` 专项，再补 `test_m164_selection_interaction.py` 或 `test_m167_candidate_selection.py`；Text/GIS 只在跨 Domain 证据不足时读取对应 Domain 文件。

工作回合结束后，将“已读文件、关键行范围、下一次唯一首读文件”压缩回本节，避免下一次从目录重新扫描。

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
