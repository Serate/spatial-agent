# M264 指标分析公共核心 Plan

状态：已完成

执行协议：`全局七维度复盘 → Capability Map → Spec → Plan → 精简实现 → Docker 验收 → 文档/提交 → 全局重规划`。

## 任务

### 1. 固化公共 seam

- [x] 新增 `agent.analysis.indicator_core` 和最小配置对象。
  - 验收：不导入 Domain；支持目录、latest/trend/compare、期间筛选、统计和来源证据。
  - 验证：M264 core contract。

### 2. 迁移两个 Provider

- [x] Economic Provider 委托 indicator-core，保留来源校验、路径发现和经济状态码。
- [x] Indicators Provider 委托 indicator-core，保留 demo fixture 和 ToolError 兼容。
  - 验收：两个 Provider 不再各自实现查询/统计/来源去重算法。
  - 验证：M251/M263 回归和静态导入检查。

### 3. 跨入口验收

- [x] 验证 Rule Runtime、ToolRegistry、Result/View、HTTP、artifact 和 SQLite/restart 的核心结果不漂移。
- [x] 对真实 Economic 数据执行一次趋势和一次比较；不把 live 模型加入默认 profile。

### 4. 阶段收口

- [x] 更新恢复卡、milestones 和中文问题日志。
- [x] Docker compileall、architecture strict、quick/stage、`git diff --check`。
- [x] commit/push 后从产品、架构、数据、模型、部署、体验、测试七个维度重规划；决定是否进入第三个专题验证。

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| Provider 错误码或结果字段变化 | 先用 adapter policy 映射，保留 M251/M263 契约 |
| 不同期间类型排序错误 | core 使用版本化 period key，并覆盖 annual/half-year/quarter |
| 核心模块变成浅 facade | 让筛选、统计、证据去重都隐藏在 engine 内，Provider 只负责输入与兼容映射 |
| 为兼容旧行为引入领域分支 | 把差异限制在配置/adapter，不在 core 判断 domain_id |

## 验证门

1. core 单测通过。
2. 两个现有 Domain 契约通过。
3. architecture strict 无反向 Domain 依赖。
4. Docker 真实 HTTP/artifact/restart 抽查通过后才提交阶段版本。

## 阶段验收证据

- `tests.test_m264_indicator_core`、`tests.test_m251_indicators`、`tests.test_m263_economic_domain`：**14/14**。
- Docker `compileall`、`architecture_check.py --strict`、quick、stage：全部通过。
- 两个 Provider 均实例化并委托 `IndicatorAnalysisEngine`；公共核心不导入 Domain Pack。
- 真实 Economic HTTP 比较：`COMPLETED`，`economic_comparison_result`，查询与来源各 1 步；容器重启后 run detail 200，artifact 200，均保留 2 steps 和 `composite` profile。
- 本阶段修复并记录了指标区域连接词和分析尾词解析问题；没有新增 Runtime、HTTP 或前端领域分支。
