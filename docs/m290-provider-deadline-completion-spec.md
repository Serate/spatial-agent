# M290 Provider Deadline 与真实 Composite 完成 Spec

## 目标

为真实 Composite planning 建立一个统一、可观测、可恢复的总 deadline：provider 请求、harness worker、异步任务和前端状态必须使用可解释的 timeout 分类；在预算内完成则继续同一 canonical plan gate，超时则安全终止规划，不创建 execution run。

## 契约

1. deadline 配置使用有界秒数，显式记录来源、预算、已用时、provider status 和 `deadline_exceeded`；不记录 prompt/响应原文。
2. provider timeout、harness timeout、network error、schema failure 和 data unavailable 分层，不互相覆盖。
3. timeout 结果保留 request/context fingerprint（若已建立）和 structured-output profile，不触发隐式重复 Planner 请求。
4. async/restart 只能接管已创建的 execution job；规划阶段 timeout 不得创建孤儿 execution run。
5. 前端展示“分析未在时间预算内完成”和安全下一步，不显示内部异常、密钥或模型原文。

## 验收

- replay contract 覆盖成功、provider timeout、harness timeout、network failure 和 deadline boundary。
- Docker lifecycle contract 证明 timeout 前后 run 创建状态、SQLite/artifact 和 recovery evidence 一致。
- 一次显式 live Composite probe 使用更合理但有界的预算；成功时继续真实 GIS/Economic 执行，失败时生成完整安全 receipt。
- 默认 CI 仍离线精简，阶段收口只执行一组集中门禁和一次 live。
