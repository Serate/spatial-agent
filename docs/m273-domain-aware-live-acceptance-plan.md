# M273 Plan：Domain-aware Live Acceptance

## 实施顺序

1. 扩展 live case contract，增加可选 `domain_id` 和 generic runtime factory forwarding；不复制 GIS/Economic 运行逻辑。
2. 增加一个 Economic trend live case，复用已有 Economic ToolRegistry、Result、View、Evidence 和真实数据。
3. 用 fake runtime 验证 Domain forwarding 与旧 factory 兼容；Docker 运行 M270/M271/M269 相邻回归。
4. 显式运行真实 Economic LLM + Docker 数据验收，再检查 provider、Planner、工具步骤、result type 和答案 evidence。
5. 更新中文恢复卡、问题日志、milestones，提交推送后重新规划是否需要真正跨 Domain 的组合 DAG。

## 设计边界

- M273 不实现跨 Economic/GIS 的单次混合 Runtime；当前 Domain Router 明确是单次选择一个 Domain，先用统一 harness 证明两个 Domain 的纵向契约一致。
- 如果后续目标要求一条请求同时执行经济与空间能力，再新增领域中立的 Composite Domain/Workflow seam，并先做 Spec/Plan；不在 live harness 中偷偷拼接两个 Runtime。
