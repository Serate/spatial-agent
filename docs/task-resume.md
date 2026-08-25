# 当前任务恢复指针

本文件不是启动文件，也不保存当前状态。新对话或上下文压缩后只执行：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1
```

当前状态入口是 [`agent-work-state.md`](agent-work-state.md)，任务进度入口是 [`../tasks/task-progress.md`](../tasks/task-progress.md)。恢复脚本默认只加载快照和任务账本最近记录；当前阶段的 Spec/Plan、最近进行中的任务和待修改文件由它们逐项指向，再按需读取。完整恢复卡、问题日志、milestones、归档和全量测试不得默认加载。

每个子任务开始、完成或暂停时，必须在 `tasks/task-progress.md` 记录状态、改动文件、Docker 验证、阻塞与下一步；再同步快照和兼容性的 `tasks/task-state.md`。阶段完成后再将稳定结论同步到 `agent-context-resume.md`、`milestones.md` 和阶段问题日志。
