# Agent 唯一恢复卡

本文件同时是恢复入口和当前状态源。新对话或上下文压缩后只执行：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1
```

不要再默认读取 `task-resume.md`、问题日志、milestones、归档、完整测试或模型响应。

## 目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。

## 当前状态

- M224 已完成：版本化 `DomainSelection`、按 Domain 隔离/缓存/恢复的 `DomainRuntimeHost`，以及 `/domains/{domain_id}/...` HTTP 边界已落地。
- SQLite 会话绑定、幂等键、run/job 清理和 artifact 均按 Domain 隔离；旧无领域路由保留为固定部署级兼容边界。
- Console 从 `/domains` 动态发现领域；运行、轮询、Action、历史和 artifact 使用领域路径，切换领域与清空对话会重置工作区。
- Docker 核心/兼容测试、quick、smoke、compileall、Node plugin smoke 和两条浏览器领域验收全部通过。

## 下一步

提交并推送 M224；随后进入 M225，新增独立、可替换的 `DomainSelector`，统一处理自然语言请求的唯一匹配、歧义澄清、无匹配和用户改选，不把选择策略塞入 Host 或前端。

## 不变量

- Runtime 领域中立；新增能力扩展 facts、catalog、schema、workflow、result/view，不写区域或固定问句分支。
- Python、测试和 `compileall` 在 Docker 中执行；默认测试离线且精简，live/GIS/HTTP/browser 仅显式验收。
- 不读取、输出或提交 API key、`.env.production`、原始模型响应、真实原始数据或私有路径。

## 读取预算

- 恢复时只加载本卡；不要先读 skill 或其他恢复文档。
- 源码先用 `rg -n -m 5` 定位，首轮最多读取 2 个源码文件和 1 个测试文件。
- 只有出现具体缺口时才有界检索历史：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1 -Topic "关键词" -MaxMatches 4 -ContextLines 8
pwsh -NoProfile -File scripts/resume_context.ps1 -Diagnostics
```

- 本卡超过 2KB 时先压缩，只保留目标、当前状态、下一步、不变量和读取预算。
