# M274 Plan：Domain Selector Provider 兼容性与自动路由

## 实施顺序

1. 先增加 selector 兼容性与 Economic catalog fallback 的精简 contract，锁定现有安全校验和旧 fallback 行为。
2. 将模型 selector 的 provider 调用改为通用 JSON object 模式；保留本地 identity schema 和 `ModelDomainSelector` 校验，不把校验下沉给中转站。
3. 为 Economic capability 增加由 Domain 声明的指标别名提示，验证 `gdp_total` 请求不会落到通用 Indicators。
4. 在 Docker 中运行新增回归、M273 及相邻 Domain/Provider/Runtime 回归、compileall、architecture strict、quick/stage。
5. 使用全新 session 做一次真实模型 `Domain auto → Economic Runtime → Result/Evidence` 验收；失败时依据 selector、planner、data execution 分层归因。
6. 更新中文恢复卡、问题日志和里程碑，提交推送后全局重规划 Composite Domain 是否值得进入下一阶段。

## 设计边界

- Provider 兼容模式只改变 wire response format，不改变模型可返回的身份集合；所有业务决策仍由本地 selector 复核。
- Economic 指标提示从 Domain catalog 生成/声明，不进入公共 Runtime，也不为洪山区或固定问句写分支。
- M274 不扩大默认网络测试；真实中转只在显式 live 命令中运行。

## 当前结论

- 离线 selector、provider fallback 和 Economic alias contract 均通过。
- 真实 selector provider 曾出现 HTTP 400、约 20 秒成功但非法 identity、transient HTTP 三类结果；三类均被有界分类并 fallback，没有泄露敏感内容。
- 全新 session 的真实 `auto → Economic` 请求最终完成两步 Economic 工具链并返回 `economic_timeseries_result`；该证据证明自动路由降级链路，不等同于纯模型 selector 稳定性。
