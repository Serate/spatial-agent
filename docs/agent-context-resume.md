# Agent 唯一恢复卡

本文件同时是恢复入口和当前状态源。新对话或上下文压缩后只执行：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1
```

不要再默认读取 `task-resume.md`、问题日志、milestones、归档、完整测试或模型响应。

## 目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。

## 当前状态

- M223 已完成：Console Shell 只通过 Renderer Registry 与 Action Host 消费 `view_specs`/Action schema，GIS 地图、样式、选择上下文和 reset 均位于 GIS plugin。
- 固定 GIS 对比 DOM/Action ID、领域控件 gate 和专用步骤摘要已删除；Text/GIS 动态表单、unknown/failure fallback、请求代次保护和清空选择均已验证。
- Docker 精简契约、quick、compileall、Node plugin smoke 与六条串行浏览器验收通过；真实 GIS/live 仍保持独立显式路径。

## 下一步

提交并推送 M223；随后进入 M224，建立多 Domain Runtime Host 和版本化 DomainSelection，让同一 HTTP/Console 部署可选择、执行并恢复 GIS/Text 运行，而不是每个服务实例固定一个 Domain。

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
