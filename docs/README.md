# 项目文档索引

本目录采用“四层文档架构”，目的是让开发者恢复任务时只读取当前阶段所需内容。

## 默认入口

新对话或上下文压缩后只需要：

1. 阅读 [`agent-work-state.md`](agent-work-state.md) 获取当前快照。
2. 运行 `pwsh -NoProfile -File scripts/resume_context.ps1` 获取有界恢复上下文。
3. 按快照指向的阶段交接文件和必要源码继续工作。

机器可读的完整索引是 [`document-index.json`](document-index.json)。

## 四层结构

| 层级 | 文件/目录 | 内容 | 默认读取 |
| --- | --- | --- | --- |
| 热状态 | `agent-work-state.md`、`tasks/current-state.md` | 当前阶段、当前任务、必要文件、阻塞和最近验证 | 是 |
| 阶段包 | `stages/Mxxx/` | 当前阶段 capability map、Spec、Plan、handoff | 只读 handoff |
| 稳定知识 | `agent-project-direction.md`、`architecture-map.md`、`api.md`、数据文档 | 长期有效的架构、产品和部署知识 | 否 |
| 历史归档 | `archive/`、旧版阶段文档、历史账本 | 已完成阶段的过程和问题 | 否 |

## 按任务读取

| 场景 | 读取内容 |
| --- | --- |
| 只恢复状态 | 热状态 + `document-index.json` |
| 开始开发 | 上述内容 + 当前阶段 `handoff.md` + 必要源码 |
| 需要理解设计 | 当前阶段 `spec.md` 或 `plan.md`，只读相关章节 |
| 查找历史 | `resume_context.ps1 -Topic "关键词"` |
| 复盘或考古 | 明确使用 `-IncludeHistory` |
| 阶段交付 | 当前阶段包 + 受影响测试 + 中文问题日志 |

## 阶段包规范

新阶段使用 `docs/stages/Mxxx/`，文件固定为：

- `capability-map.md`：模块边界、依赖方向和构建顺序。
- `spec.md`：目标、契约、边界、测试策略和验收标准。
- `plan.md`：实现顺序、任务、风险和验证点。
- `handoff.md`：当前可恢复状态，只记录实际进行中的工作。

阶段完成后冻结该目录，不把历史内容复制回热状态文件。下一阶段新建目录并更新
`document-index.json`、`agent-work-state.md` 和 `tasks/current-state.md`。

## 自动归档格式

需要自动归档的进行中账本，在文件头加入一行控制元数据：

```markdown
<!-- document-control: {"schema_version":"spatial-agent.document-control.v1","role":"active-ledger","archive_target":"docs/archive/task-progress-history.md","archive_block_prefix":"archive-block"} -->
```

已完成区块使用稳定 ID 包围，不能包围进行中的任务：

```markdown
<!-- archive-block:stage-m323-a:start -->
### M323-A：审批契约 — 已完成
...
<!-- archive-block:stage-m323-a:end -->
```

执行 `scripts/archive_document_sections.ps1 -DryRun` 可预览；确认后去掉 `-DryRun`。
脚本会把完整区块追加到控制元数据指定的归档文件，在原位置留下归档指针，并对重复归档幂等处理。
归档路径必须位于仓库内，未闭合或未标记的区块不会被处理。

## 文件命名和迁移规则

- 稳定知识使用领域名称，例如 `architecture-map.md`、`dataset-inventory.md`。
- 阶段文件使用 `Mxxx` 和稳定主题名；旧的 `docs/mxxx-*.md` 保留兼容，但通过索引访问。
- 任务状态不写入源码文件；当前状态写入 `tasks/current-state.md`，过程账本写入
  `tasks/task-progress.md`，历史账本写入 `docs/archive/`。
- 不在文档中保存 API key、Prompt、模型原文、完整私有数据或敏感异常。

## 恢复脚本

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1
pwsh -NoProfile -File scripts/resume_context.ps1 -Stage M323
pwsh -NoProfile -File scripts/resume_context.ps1 -Topic "审批" -MaxMatches 4
pwsh -NoProfile -File scripts/archive_document_sections.ps1 -DryRun
```

脚本默认只输出热状态、当前阶段交接和必要文件列表；阶段 Spec/Plan 正文必须显式读取。

索引门禁：

```powershell
pwsh -NoProfile -File scripts/validate_document_index.ps1
```

该检查只验证索引、热状态和当前阶段文件是否存在且边界正确，不读取历史正文。
