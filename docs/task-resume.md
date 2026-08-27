# 当前任务恢复指针

本文件不是启动文件，也不保存当前状态。新对话或上下文压缩后只执行：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1
```

当前状态入口是 [`agent-work-state.md`](agent-work-state.md)，它是唯一默认交接文档。任务进度入口是 [`../tasks/task-progress.md`](../tasks/task-progress.md)，恢复脚本只加载其中的“当前进行中”和“最近完成”有界区块；当前阶段的 Spec/Plan、最近进行中的任务和待修改文件由快照逐项指向，再按需读取。完整恢复卡、问题日志、milestones、归档和全量测试不得默认加载。

每个子任务开始、完成或暂停时，必须在 `tasks/task-progress.md` 记录状态、改动文件、验证、阻塞与下一步；再同步 `docs/agent-work-state.md`。`tasks/task-state.md` 只作兼容状态按需维护，阶段完成后再将稳定结论同步到 `agent-context-resume.md`、`milestones.md` 和阶段问题日志。

实现优先规则：上下文预算优先用于契约、核心代码、集成和问题定位。开发中只做能区分当前独立失败模式的最小检查，阶段收口集中运行精简门禁；不按子任务数量重复测试，不把全量回归作为默认恢复或每次小改动的前置条件。
