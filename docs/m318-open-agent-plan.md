# M318-M325 实施计划

## M318：契约与基线

- 建立 Execution Policy、ReAct Decision、ReAct Evidence、Web Evidence、Tool Proposal 和 Approval 契约。
- 建立真实模型 full ReAct、网络搜索默认开启、工具提案默认开启的配置矩阵。
- 保留 Rule/Replay 离线适配器和旧 TaskPlan/RunEvent 兼容。
- 更新任务账本、交接快照和中文问题日志规范。

验收：契约测试、Docker compileall、architecture strict；不调用真实模型。

## M319：通用执行策略

- 实现 `ExecutionPolicyResolver`。
- 支持 direct tool、generated DAG、Domain workflow、ReAct。
- 取消所有能力必须绑定 workflow 的限制。
- 保留高风险 Domain workflow、权限和数据 readiness 门禁。
- 接入同步、异步、SQLite、artifact 和重启恢复。

验收：四种策略矩阵、权限/数据/结果类型失败、HTTP 和跨入口 identity。

## M320：全量真实模型 ReAct

- 实现单动作、有限轮次、重复动作检测、空转检测和预算控制。
- 将中间结果压缩成安全摘要与引用。
- 支持工具调用、继续决策、澄清、有限修复、取消和恢复。
- 将轮次和动作写入 RunEvent/Evidence。
- 复用现有最终答案流。

验收：简单、单步、多步、结果依赖、澄清、非法动作、超时、恢复；阶段收口一次真实模型验收。

## M321：白名单网络搜索

- 实现搜索适配器、公共网页抓取和 `document_evidence`。
- 增加白名单、大小、重定向、超时、结果数和总网络预算。
- 将搜索接入 ReAct，并在答案中展示来源引用。
- 网络失败、白名单缺失和页面不可读时返回结构化降级。

验收：fake provider、URL/域名/超时/大小/重复搜索；显式真实网页验收一次。

## M322：Python 工具提案与沙箱

- 实现工具提案 schema、源代码 hash 和 sandbox receipt。
- 使用 Docker 无网络、只读挂载、独立临时目录和资源限制。
- 禁止密钥、任意文件、网络、子进程、动态执行和依赖安装。
- 沙箱输出重新经过 JSON、schema、Result Contract 和预算校验。

验收：合法纯计算、参数错误、输出错误、超时、资源限制和未授权访问拒绝。

## M323：人工审批与 Registry 治理

- 实现提案状态机：`PROPOSED → VALIDATING → AWAITING_APPROVAL → APPROVED → REGISTERED`。
- 支持拒绝、过期、撤销、版本和 hash 变化重新审批。
- 持久化提案、artifact、校验、审批和注册证据。
- 禁止公共 HTTP 直接注册 callable；内部可信注册与公共路径分离。

验收：未审批不可执行、审批后可执行、撤销/过期/重启恢复、CLI/HTTP/SQLite 一致。

## M324：前端、SSE 和恢复整合

- 展示 ReAct 轮次、当前动作、工具状态、来源、审批和恢复进度。
- 分析过程摘要默认收起，不显示 Prompt 或思维链。
- 复用答案逐字流、SSE、Last-Event-ID、心跳和 polling fallback。
- 收敛 FastAPI 与 stdlib 入口的重复传输胶水。
- 继续由动态 Result/View 展示 GIS、栅格、矢量、指标、文本和文档证据。

验收：Node/browser smoke、SSE 断线、服务重启、CLI/HTTP/前端结果 identity。

## M325：完整受控路线验收

- Docker + 本地真实 GIS + 真实模型完成复杂多步骤请求。
- 验证默认 ReAct、默认白名单搜索和来源引用。
- 验证工具提案、沙箱、人工审批、注册和执行。
- 复核延迟、token、动作数量、恢复和答案流。
- 更新 README、中文问题日志、阶段摘要并提交推送。

验收：真实模型 + Docker/GIS 至少一条完整链路成功；默认 CI 保持离线精简。

## 每阶段交付门禁

每阶段均执行：实现 → 受影响契约 → Docker 精简门禁 → 文档交接 → 全局重规划 → commit/push。
真实 Provider 失败只记录安全 receipt，不重复提交同一请求。
