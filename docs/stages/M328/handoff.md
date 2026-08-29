# M328 阶段交接

## 状态

- 阶段：`M328` 受控开放行动闭环
- 状态：M328-A～E 已完成；阶段已收口，等待提交推送
- 恢复入口：优先读取 `docs/agent-work-state.md`、`tasks/current-state.md`、本文件和 `plan.md` 当前批次。

## 已知基线

- M327 已完成 descriptor、capability selection、跨类型 result summary 和跨入口 Console projection。
- M327-E 已完成真实 GIS+经济 Composite、多步经济+Web 搜索降级、真实 proposal sandbox 校验和答案流验收。
- 当前默认配置为 full ReAct、Web 搜索开启、工具提案开启；ToolRegistry、有限 Schema、AST、sandbox 和人工审批门禁保持不变。

## M328-A 交付

- 审批记录新增有界 `run_id`，并继续以 `receipt_fingerprint` 与 approval `version` 保护绑定；旧 SQLite payload 可兼容读取。
- `RuntimeToolApprovalResume` 闭合审批后的运行路径：只有绑定存在且身份一致才继续原 ReAct run；拒绝、撤销、过期关闭运行且不执行。
- ReAct loop 支持从安全历史/证据和 action budget 继续，动态审批工具会刷新 execution-policy allowlist；不重新规划原请求。
- Service approval 入口会发布工具并把结果重新投影到统一 Run/Artifact/异步契约；重复审批保持幂等。
- Docker M328-A 专项 `3/3` 与 M322/M323/M324 相邻回归 `26/26` 通过；未保存 source、example、Prompt 或模型原文。

## 下一步

从 M328-C 开始，使用少量真实模型请求覆盖经济、指标、GIS 降级、Web 搜索和工具提案恢复；只读取对应验收脚本、
紧凑测试与失败时的边界实现，不重新加载 M327 全量源码、完整历史或模型输出。

## M328-C 当前交接

- 审批恢复已实现：批准后仅恢复同一 `run_id`、proposal version 和 receipt fingerprint 的原 ReAct 运行；拒绝、撤销、
  过期或身份不一致不会执行动态工具。
- 动态工具已实现：ReAct Planner 使用 Runtime 当前 Registry 工具目录；审批绑定刷新策略 allowlist，但基础 Provider
  工具集合保持稳定，避免异步 Runtime context 指纹漂移。
- Web evidence 已实现：成功、无结果和网络不可用均使用同一有界 document evidence；只展示安全 source record，不能把
  网络失败当作网页来源。
- 已完成的真实验收（脱敏）：经济多步本地数据 + `web_search` 共 4 个工具步骤，Web 返回
  `unavailable/search_network_error`；真实动态工具完成 proposal → sandbox → 人工审批 → 同一 Run 恢复 → 实际执行；
  两者均启用答案流，SSE Last-Event-ID 续传通过。
- 收口完成：M322/M323/M324/M328 紧凑回归 `32/32`；Docker readiness `200`、compileall、architecture strict、代码/文档
  索引和前端 smoke 通过。真实经济数据 + Web 搜索 4 步请求完成，SSE 420 事件/Last-Event-ID 续传通过；真实经济 +
  区域指标 Composite 两组件完成；真实工具提案审批后同一 Run 恢复并执行成功。
- 复杂请求边界：过宽请求在缺少具体指标或模型字段不符合契约时结构化澄清/拒绝，不创建 Run；该结果已记录为安全降级，
  不把 Provider 漂移或缺失数据误报成成功。
- 安全：验收仅记录脱敏状态、计数、动作名、reason code、fingerprint 和 token usage；未保存密钥、Prompt、模型原文、
  网页正文、工具 source 或私有路径。
- 下一阶段：先做全局重规划，再决定是否扩展跨域能力或体验；恢复时不重新读取 M327 全量源码、完整历史和模型输出。
