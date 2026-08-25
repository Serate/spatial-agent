# M272 Plan：开放式 LLM 多步验收

## 实施顺序

1. 先做 provider probe，确认真实外部依赖可达；失败时停止昂贵的多步 case。
2. 用 memory backend 跑真实 LLM 开放空间总览，检查计划生成、步骤 DAG、结果类型和 safe evidence。
3. 用 local GIS 跑同一请求，检查真实数据执行；用 Rule Planner local 对照，分离模型失败与 GIS 失败。
4. 对 timeout 进行短 provider timeout 对照，确保 live CLI 不把 provider timeout 伪装成 harness deadline。
5. 只在验收边界发现缺陷时修改代码；然后运行 Docker 定向回归、compileall、architecture strict、quick/stage，更新中文文档并推送阶段版本。

## 当前结论

- provider probe READY；memory + 真实 LLM 通过；Rule Planner + local GIS 通过；真实 LLM + local GIS 在 45 秒 provider timeout、90 秒 harness deadline 下通过。
- 一次 20 秒 provider timeout 对照失败且 0 工具步骤，随后较宽 timeout 成功，说明中转 latency 有波动；不构成 GIS/Runtime 缺陷。
- M270 事件语义补丁只区分 provider timeout 与 harness deadline，不改变业务执行路径。
