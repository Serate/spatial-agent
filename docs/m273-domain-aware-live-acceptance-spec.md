# M273 Spec：Domain-aware Live Acceptance

## 目标

让同一个 live baseline harness 通过 case 声明选择已注册 Domain Pack，从而用同一套 Result/Evidence 评估 GIS 与 Economic 的真实 LLM 链路。Domain 选择只改变 composition root，不把 Domain 专用判断写进 Runtime、Planner 或前端。

## 接口

- live case 可选 `domain_id`，值只作为已注册 Domain 的 bounded identity 传给 `runtime_factory`。
- 没有 `domain_id` 的旧 case 继续调用 `runtime_factory(planner, backend)`；带 `domain_id` 的 case 调用 `runtime_factory(planner, backend, domain_id=...)`。
- baseline 按 `backend + domain_id` 缓存 Runtime，避免同一 Domain 的多条 case 重建配置；结果 evidence 显示 bounded `domain_id`。
- 现有 `expected_tools`、`expected_result_type`、plan quality、registry completeness 和 answer 评估保持不变。

## 验收

1. GIS 既有 live cases 行为不变。
2. Economic trend case 能通过同一 baseline 选择 Economic Domain，并校验 `economic_indicator_query`、`economic_source_evidence` 和 `economic_timeseries_result`。
3. 自定义 runtime factory 只需实现同一个可替换 seam；旧的两参数 factory 仍兼容。
4. 真实 Docker + LLM + Economic 数据完成年度趋势，结果、来源证据和安全 metrics 可投影。
5. 默认 CI/quick/stage 不联网；真实多 Domain cases 只通过显式 live 命令选择。
