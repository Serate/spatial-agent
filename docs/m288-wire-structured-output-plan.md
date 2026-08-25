# M288 Provider Wire-level Structured Output Plan

## 实施顺序

1. **A 全局规划**：冻结 provider profile、mode negotiation、evidence 和不放宽 schema 的边界。
2. **B Wire capability contract**：抽取 provider-neutral structured-output profile，覆盖 config/probe/default 来源和版本校验。
3. **C Client/Planner adapter**：让 OpenAI-compatible client 按 profile 发送 strict schema 或 documented json object；Planner 仍只接收 JSON object。
4. **D 跨入口 evidence 与体验**：同步 mode/readiness/fallback evidence 到 planning、async/artifact/restart、live receipt 和 Console projection。
5. **E 集中验收与交付**：运行少量 replay/contract、Docker 门禁和一次真实 live，更新中文日志、提交推送并全局重规划。

## 测试节奏

- 开发中只运行当前 wire seam 的最小 contract/compile 检查。
- B～D 完成后集中运行一个 M288 contract，并联合 M287 相邻门禁；不按 provider 模式重复跑全量。
- 阶段末执行一次 Docker/HTTP/readiness/前端 projection 和一次显式 live；默认 CI 不联网。

## 风险控制

- 中转忽略 schema：保留本地严格校验；mode 只改善请求兼容性，不改变结果安全边界。
- provider profile 欺骗：profile 只影响 wire 参数，所有模型输出仍由应用验证。
- fallback 扩散：只能在 provider adapter 内声明和记录，不能落入 Domain/Runtime/Console 专用判断。
