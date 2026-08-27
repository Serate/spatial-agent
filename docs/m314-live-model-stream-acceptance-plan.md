# M314 真实模型流式验收实施计划

## A：建立安全反馈闭环

- 复用现有 live provider、HTTP acceptance、RunEvent 和浏览器脚本，新增一个 M314
  有界验收入口，统一输出 7 场结果摘要。
- 报告只保存安全元数据；每个场景最多一次显式提交，受控失败场景不自动重复提交。
- 先执行 Docker readiness、compileall、architecture strict、M313 答案流契约和已有
  前端 smoke，确认问题属于 live 边界还是已有代码。

## B：真实模型与跨入口验收

- 正常路径验证阶段事件、工具状态、答案 delta、最终 Result/Evidence/artifact。
- 上下文场景验证 session identity、前后请求关联和追问答案不丢失。
- 澄清场景验证结构化缺口、无 execution Run 和安全恢复动作。
- Provider 场景验证 timeout/failure receipt、一次有限重试、手动重试入口和终态事件。
- SSE 场景复用成功 Run 验证首段读取、断线续传、轮询 fallback 与重启恢复，不重新调用模型。

## C：问题修复边界

- 规划长期等待：补充真实阶段事件、心跳、耗时和 provider 失败终态投影。
- 事件传输：修复游标、重连、终态或轮询切换造成的重复/丢失。
- 答案传输：修复 delta 队列、终态排空、最终文本校正和 fallback 标记。
- 前端体验：只展示用户可读状态、结论和恢复操作；技术详情保持可折叠。

## D：收口

- Docker 集中运行最小必要 Python/Node/HTTP/浏览器验证，并执行一次完整 7 场 live。
- 更新 `docs/agent-work-state.md`、`tasks/task-progress.md`、`tasks/task-state.md` 和
  `docs/agent-development-issues.md`。
- 确认未带入密钥、Prompt、模型原文或 `.playwright-mcp/`，提交并推送阶段版本。

## 阻塞规则

若中转 Provider 在预算内持续不可达，停止重复请求，保留脱敏失败证据，并用离线
replay 验证 fallback；不能把 Provider 超时伪装成 Runtime 或 GIS 成功。

## 当前执行结果

- Provider 配置更新后，Docker 探测为 `READY`；DeepSeek + 本地 GIS 的最小真实请求为
  `COMPLETED`，规划 1 次、0 重试，artifact/evidence/polling 对照通过。
- 同一成功 Run 的 SSE 共返回 384 个事件，其中 368 个 `answer_delta` 和 1 个终态事件；
  `Last-Event-ID: 1` 能完整续传至第 384 个事件。
- 已复现并修复 100 条分页导致终态丢失的问题；新增回归先失败后通过。
- 已将规划和回答的 provider 预算分离：规划保持阶段预算，回答默认 20 秒、768 token、
  0 重试，并支持 `OPENAI_ANSWER_*` 覆盖。
- 本轮不重复执行昂贵的多场景 live 组合；已有失败 Run 仅作为脱敏失败边界证据，未将
  Provider 401/404 误报为 GIS 或 Runtime 故障。
