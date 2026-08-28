# 当前任务恢复指针

本文件不是启动文件，也不保存当前状态。新对话或上下文压缩后只执行：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1
```

脚本默认读取 [`agent-work-state.md`](agent-work-state.md)、[`document-index.json`](document-index.json)、
[`../tasks/current-state.md`](../tasks/current-state.md) 和当前阶段的 `handoff.md`。当前阶段的
capability map、Spec、Plan 只输出路径，不默认读取正文；源码和测试根据交接文件逐项读取。
完整恢复卡、问题日志、milestones、历史账本、归档和全量测试不得默认加载。

按阶段恢复：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1 -Stage M323
```

按主题查找历史（仍然有界）：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1 -Topic "sandbox" -MaxMatches 4
```

只有明确需要时才使用 `-IncludeHistory`；它不会成为默认恢复路径。

归档已完成进度区块：

```powershell
pwsh -NoProfile -File scripts/archive_document_sections.ps1 -DryRun
pwsh -NoProfile -File scripts/archive_document_sections.ps1
```

归档脚本只处理带 `document-control` 和成对 `archive-block` 标记的完整区块；建议先 dry-run。

每个子任务开始、完成或暂停时，必须先更新 `tasks/current-state.md`，再追加到
`tasks/task-progress.md` 并同步 `docs/agent-work-state.md`。`tasks/task-state.md` 只作兼容状态按需维护，
阶段完成后再将稳定结论同步到 `agent-context-resume.md`、`milestones.md` 和阶段问题日志。

实现优先规则：上下文预算优先用于契约、核心代码、集成和问题定位。开发中只做能区分当前独立失败模式的最小检查，阶段收口集中运行精简门禁；不按子任务数量重复测试，不把全量回归作为默认恢复或每次小改动的前置条件。
