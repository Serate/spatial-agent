# Plan：M325 真实模型 + Docker/GIS + 白名单搜索纵向验收

> 执行顺序：全局复盘 → capability map → Spec → 验收准备 → 真实纵向执行 → 最小修复 →
> 集成验收 → 交接与全局重规划。单 Agent，最大并发度 1。

## M325-A：Provider 显式探针

- [x] 检查容器内 provider 配置来源、base URL、模型名和结构化输出模式，仅输出存在性与安全摘要。
- [x] 运行一次有界真实 provider probe；记录成功或安全错误 receipt，不保存模型原文。
- [x] 若失败，先区分中转/官方兼容协议、超时、权限和响应格式，不盲目重试。

## M325-B：Docker/GIS 数据就绪

- [x] 检查容器挂载、analysis-ready manifest、DEM/矢量数据健康和 CRS/对齐证据。
- [x] 使用真实本地 backend 运行一个不依赖固定关键词的 GIS 结果请求。
- [x] 若数据缺失，修复配置或返回明确降级；不把内存演示后端当作真实 GIS 成功。

## M325-C：白名单搜索边界

- [x] 读取服务器白名单配置，不在请求中接受任意 URL 或 headers。
- [x] 用 fake opener 做离线策略契约：成功白名单来源、越界来源、重定向和超大响应。
- [x] 在真实验收中仅当配置明确允许时调用白名单 provider，并保存来源摘要而非网页原文。

## M325-D：真实模型 ReAct 纵向切片

- [x] 发送 Spec 中的开放请求，使用真实模型、Docker local backend、默认 ReAct 和显式预算。
- [x] 核对事件序列、工具调用、结果数据形态、降级原因、最终答案和 token/延迟摘要。
- [x] 至少覆盖一次工具成功和一次模型/数据不可用时的安全恢复；不重复调用同一失败 provider。

## M325-E：交付一致性

- [x] 对成功或安全降级 run 检查 HTTP 结果、轮询、SSE/事件回放、artifact 和重启恢复的核心字段。
- [x] 前端只验证用户可见的阶段、答案、结果、地图/证据入口和错误提示，不验证内部实现文案。
- [x] 运行 compileall、architecture strict、索引校验和 readiness；不运行无关全量测试。

## M325-F：阶段收口

- [x] 更新 `docs/agent-work-state.md`、`tasks/current-state.md`、`tasks/task-progress.md`、
  中文问题日志和本阶段 handoff。
- [x] 归档本阶段详细过程，更新 document/code index。
- [x] 判断是否需要通用代码修复；若需要，补最小契约并重新执行受影响验收。
- [x] 完成全局重规划和版本交付；不把真实私有配置、模型原文或数据复制进仓库。

## 门禁

| 门禁 | 默认 | M325 |
|---|---:|---:|
| M325 后端紧凑契约 | 否 | 必要时 |
| M320/M321 受影响契约 | 否 | 必要时 |
| 真实 provider | 否 | 显式一次 |
| Docker/GIS | 否 | 显式一次 |
| 白名单网络 | 否 | 有配置才执行 |
| compileall/architecture/index/readiness | 否 | 阶段收口 |
