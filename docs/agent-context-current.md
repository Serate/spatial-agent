# Agent 当前恢复卡

这是上下文压缩或新对话接续时的唯一默认入口。只用本卡恢复当前切片，不重读项目历史。

## 恢复门禁

1. 默认只读本文件，然后执行 `git status --short --branch` 和 `git log -1 --oneline --decorate`；不要因为文件名是 resume、task 或 issues 就自动打开历史档案。
2. 只确定一个“当前唯一工作切片”，不要自动打开其他文档、源码、测试、完整日志或模型响应。
3. 需要证据时先用 `rg -n -m 5 "关键词|符号|错误" 文件` 定位，再只读取附近有限行，例如：
   `Get-Content 文件 | Select-Object -Skip 120 -First 60`。
4. 默认读取预算：历史文件为 0 个；只有当前卡给出明确关键词后，才读取 1 个历史文件的 1 个命中区间（不超过 40 行）、最多 2 个源码文件和 1 个直接相关测试文件。超过时先说明原因。
5. 历史档案只用于审计，不是恢复入口；`agent-context-resume.md`、`task-resume.md`、`agent-development-issues.md` 和 `milestones.md` 不得全文读取。
6. 只保留状态、提交、证据引用、阻塞项和下一步；大日志、原始模型响应、完整 GeoJSON 和测试输出只保留摘要或路径。

### 恢复操作的最小模板

```text
1. 读取 docs/agent-context-current.md
2. 查看 git status --short --branch 与 git log -1 --oneline --decorate
3. 按“当前唯一工作切片”选择一个动作
4. 只有遇到具体未知项时，先 rg 定位，再读取命中附近的有限行
```

如果用户要求追溯历史，先明确需要的阶段或关键词，再按区间读取；不要为了“了解背景”批量加载多个历史文档。

历史档案 `docs/agent-context-resume.md`、`docs/task-resume.md`、`docs/milestones.md`、
`docs/agent-development-issues.md` 均按需查询，不是恢复入口；必须先精确定位，再读取命中段。

## 当前状态

- 总目标：建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。
- 当前阶段：M216，真实模型失败/修复/降级与 geometry 按需恢复。
- 最近提交：`8d08ec6 docs: advance recovery card to m216`；最近功能提交为 `4fd8b27 test: add explicit live GIS acceptance path`，M215 已完成。
- M216 当前未提交改动已补充 `artifact-reference.v1`：Result、Geometry、Artifact、Async 和 Console 共用安全的按需引用；Docker 27 项专项、核心评测 7/7、HTTP 引用检查和 Console 地图 smoke 已通过。
- 容器：`ai-agent-spatial-agent-1` 应保持 healthy；Python 测试和 compileall 默认在 Docker 中执行。
- 已通过：M200–M215 的跨入口、恢复、证据、Node/Chrome/DOM smoke、生产 acceptance、action/async recovery、复杂 GIS Docker 和 live model 专项。
- 当前无已知阻塞；M206 地图清理、M207 preview、M208 lifecycle、M209 repair lineage、M210 receipt、M211 failure/replay、M212 failure envelope、M213 async evidence、M214 complex cross-entry 和 M215 live acceptance 均已通过。

## 当前唯一工作切片

1. 用脱敏 replay 覆盖无效 JSON、工具参数错误、超时和 provider 不可用，核对有限 repair/澄清/拒绝与 fallback 生命周期。
2. 已完成 Docker live-short 2/2 与 geometry artifact smoke；确认真实模型路径、已有 Artifact 读取和 `artifact-reference.v1` 一致。
3. 收口敏感信息检查；提交、推送并做全局重规划。

## 不变量

- Runtime 决定生命周期和 `allowed_actions`；Domain guidance 只能提供 advisory 建议。
- 不为单一区域、固定问句或 GIS 页面增加 Runtime 硬编码。
- 默认 quick/CI 离线、精简；真实模型、GIS、Docker、HTTP、浏览器属于显式验收路径。
- 不提交 API key、`.env.production`、私有模型响应、原始 GIS 数据或仓库外 evidence。
- 阶段完成顺序：全局规划 → 实现 → 精简集成测试 → 更新本卡/阶段文档 → 提交推送 → 全局重规划。

## 按需入口

- 项目方向：`docs/agent-project-direction.md`
- 阶段历史：`docs/task-resume.md` 或 `docs/milestones.md`（先 `rg`）
- 中文问题日志：`docs/agent-development-issues.md`（先按错误关键词 `rg`）
- 恢复历史：`docs/agent-context-resume.md`（仅需追溯时读取）

Docker 重建：

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --force-recreate
```

每完成一个阶段，只更新本卡的状态、证据引用和下一步；详细过程留在历史文档，禁止把长日志复制回本卡。
