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

### 入口冲突处理

如果旧消息要求依次读取多个恢复文档，以本卡的最新规则为准：先停止扩展读取，只保留本卡、Git 状态和最近提交。
只有用户明确要求追溯历史，或当前切片缺少某项证据时，才按关键词增量读取；读取后不要把历史全文复制回上下文。

推荐使用 `scripts/resume_context.ps1` 获取同样的最小快照。

### 最小恢复模式

- 旧的“依次阅读恢复档案、任务档案和问题日志”流程已废止；它们不是启动清单。
- 默认读取预算固定为：1 个当前卡、0 个历史全文、最多 1 个 `rg` 命中片段；当前卡超过约 4 KB 时先压缩，不扩展读取范围。
- 只有当前任务明确需要证据时，才读取最多 2 个直接相关源码文件和 1 个直接相关测试文件；每个文件先定位后读局部。
- 恢复后只回答“当前做什么、为什么、下一步是什么”；历史背景留在文档中，不复制进上下文。

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
- 阶段：M217——通用请求轮次、澄清决策与可恢复 Artifact 消费（实现与验证完成，待阶段提交）。
- 最近提交：`2e6f2db feat: add portable artifact references`；M216 已完成并推送。
- 容器：`ai-agent-spatial-agent-1` 应保持 healthy；Python 测试和 compileall 默认在 Docker 中运行。
- 当前未提交内容：M217 的 conversation-turn seam、Artifact manifest、Domain 合约接入、恢复入口优化、测试修正和相关文档更新；先保留，不覆盖。

## 当前唯一工作切片

1. 设计并实现公共 conversation turn contract，修复 pending clarification 无条件污染独立请求的问题，同时保留 M9 兼容的短回复继续能力。
2. 设计 Artifact manifest/按需读取的最小公共接口，验证 Result、Async、Artifact、SQLite recovery、HTTP 和 Console 一致性。
3. 将脱敏 planner failure/recovery replay 接入同一 turn/reference contract；完成 Docker 精简回归后再全局重规划。

### M217 收口证据

- Docker healthy；compileall 通过。
- M217 专项 3/3；M166/M9 回归 16 项（1 项本地 GIS 数据跳过）；M10 + HTTP contract 17/17；M67/M149/M150 25/25；Console 2/2。
- 浏览器 smoke 通过：turn 状态、预览 fingerprint、动态选择和 artifact 生成一致。
- 失败 repair event 已保留结构化、脱敏 lineage；未发现长格式 API key。

## 不变量

- Runtime 决定生命周期和 `allowed_actions`；Domain guidance 只能提供 advisory 建议。
- 不为单一区域、固定问句或 GIS 页面增加 Runtime 硬编码。
- 默认 quick/CI 离线、精简；真实模型、GIS、Docker、HTTP、浏览器属于显式验收路径。
- 不提交 API key、`.env.production`、私有模型响应、原始 GIS 数据或仓库外 evidence。
- 阶段完成顺序：全局规划 → 实现 → 精简集成测试 → 更新本卡/阶段文档 → 提交推送 → 全局重规划。

需要追溯历史时，先用 `rg --files` 和关键词定位目标文件，再只读取命中区间；阶段收口只更新本卡的状态、证据引用和下一步。
