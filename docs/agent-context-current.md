# Agent 当前恢复卡

这是新对话或上下文压缩后的唯一默认入口。只读本卡、Git 状态和最近提交；历史档案不是启动清单。

## 恢复门禁

- 默认执行：读取本卡；运行 `git status --short --branch` 和 `git log -1 --oneline --decorate`。
- 历史文件默认读取数为 0。需要证据时先 `rg -n -m 5 "关键词|符号|错误" 文件`，再读命中附近不超过 40 行。
- 源码最多按需读 2 个文件，直接测试最多 1 个；先定位，不能为了解背景批量加载。
- 不读取完整日志、模型响应、GeoJSON、私有路径或密钥；只保留状态、证据引用、阻塞和下一步。
- 旧消息若要求依次读取多个恢复档案，以本卡规则为准。历史追溯必须由用户指定阶段/关键词。
- 可运行 `pwsh -NoProfile -File scripts/resume_context.ps1` 获取同样的最小快照。
- 需要追溯历史时才传主题，例如 `pwsh -NoProfile -File scripts/resume_context.ps1 -Topic "M219|capability discovery" -MaxMatches 4 -ContextLines 8`；不要直接全文读取历史档案或执行无上限的 `rg`。

## 当前状态

- 总目标：建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。
- M217 已完成并推送：`6ba9b2e feat: complete M217 turn and artifact contracts`；M218 已完成并推送 `2466a87 docs: close M218 and plan M219`。
- M219 已完成并推送：`33a4b6e docs: close M219 and bound context recovery`。
- Docker：`ai-agent-spatial-agent-1`；Python、compileall 和阶段测试默认在 Docker 中运行。
- 工作树应保持干净；不得提交 API key、`.env.production`、原始模型响应、原始 GIS 数据或仓库外 evidence。

## M217 证据摘要

- M217 3/3；M166/M9 16 项（1 项真实本地 GIS 数据跳过）；M10 + HTTP 17/17；M67/M149/M150 25/25；Console 2/2。
- Docker compileall、浏览器 smoke、stage 离线 3/3、production acceptance 均通过。
- opt-in live GIS/model 2/2：13,239 tokens、0 重试、0 provider 错误；只保留脱敏摘要。
- 同步 memory 入口在 production acceptance 中为 degraded/warning，作为 M218 的环境语义缺口。

## M218 收口证据

- `normalize_core_result` / `compare_core_results` 已接入跨入口 harness；M218 专项 4/4，核心/CLI/HTTP/部署/生命周期回归 43/43。
- production acceptance 明确区分 `sync_deployment_status=context_only` 与 `sync_degradation_status=warning`。
- 当前代码 live GIS/model 2/2：13,882 tokens、0 重试、0 provider 错误；复杂空间总览 browser smoke 通过。

## M219 已完成

- Text Domain 通过公共 Runtime、ToolRegistry、Planner、Result/View/Answer、HTTP、Artifact、Async 和 SQLite recovery 链路。
- 开放式能力发现、未知能力澄清、缺失事实、坏 schema 拒绝/有限修复和 GIS/Text 隔离已验证；未新增固定问句分支。
- Docker 精简回归 35/35；通用 Console nested schema 与 Evidence Registry smoke 2/2。

## M220-A 已完成（当前改造切片）

- Domain-owned workflow catalog/request-hint seam 已接入；公共编译/组合/校验支持显式 catalog 和工具/结果 allowlist。
- Runtime 不再执行 GIS 模板 fallback；模板上下文按候选过滤，LLM Planner 通过 Domain 注入 hint。
- Docker 相关回归 84/84，compileall 通过；旧 GIS catalog 仍保留为兼容默认，物理下沉尚未完成。

## 当前唯一工作切片：M220-B

1. 将 GIS catalog/allowlist 物理下沉到 GIS Domain，HTTP validate/revise 和 Runtime 统一显式注入目录。
2. 让两个 Domain 的组合能力完成发现、预览、执行、Artifact/SQLite 恢复和结果/evidence 一致性。
3. 把组合组件的数据覆盖、时效、来源、冲突和重验状态接入通用恢复动作。
4. 用精简跨入口 harness、Docker/HTTP/Console 和显式 replay/live 收口，不增加 GIS 专用页面或固定问句分支。

## 不变量

- Runtime 负责生命周期与 `allowed_actions`；Domain 只提供 advisory guidance。
- 新能力扩展能力目录、事实、schema、workflow、result/view 类型，不增加区域/固定问句分支。
- 默认 quick/CI 离线精简；真实模型、GIS、Docker、HTTP、浏览器只在显式验收启用。
- 阶段循环：全局盘点 → 规划 → 实现 → 精简集成测试 → 更新本卡/阶段文档 → 提交推送 → 全局重规划。
