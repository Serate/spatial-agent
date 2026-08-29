# Spec：M328 受控开放行动闭环

## Objective

让通用 Agent Runtime 能稳定处理开放请求中的三类行动：调用已注册工具、检索白名单网页、提出一个
沙箱 Python 工具。每类行动都必须产生结构化 evidence；工具提案在 Schema/AST/sandbox 通过后停在人工
审批，审批、拒绝、恢复和重启不能丢失运行 identity。

## Public contract

1. ReAct decision 仍是一轮一个动作；结构化计划/参数先校验，只有已接受动作才能执行。
2. Web search 只接受服务器配置的 HTTPS provider 和 allowlist；结果只保留有界 title/url/domain/snippet，
   网络失败返回 `unavailable` 与稳定 reason code。
3. Tool proposal 只允许有限 JSON Schema 和纯 `run(arguments)` Python；receipt 只传播 hash、状态、检查项和
   sandbox profile，不传播 source 或 example_arguments。
4. `WAITING_FOR_DECISION` 是可恢复终态前的持久状态；审批动作必须带版本和 fingerprint，过期/撤销绑定不能执行。
5. 答案只消费 Result Summary/Evidence；用户可见内容为结论、限制和来源，不展示隐藏思维链、Prompt、密钥或原始模型输出。

## Acceptance

- 一个真实模型 + Docker/GIS 请求完成多步数据分析，并通过 Artifact、轮询、SSE 和答案流对照。
- 一个真实模型请求实际调用 `web_search`；成功或网络降级均明确可审计，不能伪造来源。
- 一个真实模型请求提出纯计算工具，sandbox 校验后进入 `WAITING_FOR_DECISION`，未审批前没有工具步骤。
- 审批/拒绝/重启恢复和跨入口读取保持相同 receipt identity。
- 默认只运行精简离线回归；真实模型、真实网页和 Docker 验收显式执行。

## Verification policy

优先运行受影响的 ReAct、搜索、proposal/approval、结果摘要和跨入口契约；文档/样式改动可不跑测试。
真实验收只记录脱敏状态、动作名、计数、reason code、耗时和 token usage，不保存模型正文、网页正文、密钥或私有数据。
