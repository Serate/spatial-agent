# Agent 当前恢复卡

这是上下文压缩或新对话接续时的唯一默认入口。只用本卡恢复当前切片，不重读项目历史。

## 恢复门禁

1. 只读本文件，然后执行 `git status --short --branch` 和 `git log -1 --oneline --decorate`。
2. 只确定一个“当前唯一工作切片”，不要自动打开其他文档、源码、测试、完整日志或模型响应。
3. 需要证据时先用 `rg -n -m 5 "关键词|符号|错误" 文件` 定位，再只读取附近有限行，例如：
   `Get-Content 文件 | Select-Object -Skip 120 -First 60`。
4. 默认读取预算：1 个历史文件的 1 个命中区间（不超过 60 行）、2 个源码文件和 1 个直接相关测试文件。超过时先说明原因。
5. 只保留状态、提交、证据引用、阻塞项和下一步；大日志、原始模型响应、完整 GeoJSON 和测试输出只保留摘要或路径。

历史档案 `docs/agent-context-resume.md`、`docs/task-resume.md`、`docs/milestones.md`、
`docs/agent-development-issues.md` 均按需查询，不是恢复入口；必须先精确定位，再读取命中段。

## 当前状态

- 总目标：建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。
- 当前阶段：M213，Run/Action/Async/SQLite/Artifact 的统一执行 envelope。
- 最近功能提交：`b61c39e feat: expose action execution envelope on failure`；M212 已完成，待本卡更新后推送。
- 容器：`ai-agent-spatial-agent-1` 应保持 healthy；Python 测试和 compileall 默认在 Docker 中执行。
- 已通过：M200–M212 的跨入口、恢复、证据、Node/Chrome/DOM smoke、生产 acceptance 和 action failure/replay Docker 专项。
- 当前无已知阻塞；M206 地图清理、M207 preview、M208 lifecycle、M209 repair lineage、M210 receipt、M211 failure/replay 和 M212 failure envelope 回归均已通过。

## 当前唯一工作切片

1. 盘点 `execution-record.v1` 在 Run、Action、Async、SQLite、Artifact-only recovery 和 Console 的现有投影与缺口。
2. 只在跨入口核心结果、错误、lifecycle、receipt 或 recovery 不一致时补公共契约，不增加 GIS 页面分支。
3. 用 Docker 跑精简 Run/Action/Async cross-entry 专项，更新阶段摘要和本卡；阶段完成后提交、推送并做全局重规划。

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
