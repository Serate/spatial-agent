# Plan：M327 开放请求能力发现与结果质量

> 顺序：全局重规划 → Capability Map → Spec → 契约冻结 → 实现 → 最小验证 → Docker 验收 →
> 交接更新 → 全局重规划 → 提交推送。单 Agent，最大并发度 1。

## M327-A：能力描述契约

- [x] 盘点现有 Catalog、Result profile、RequestFacts 和 readiness 字段，确定最小通用描述。
- [x] 增加版本化 descriptor 投影：输入事实、输出类型、前置条件、证据要求和成本提示。
- [x] 为未知字段、缺失能力和旧 descriptor 建立 fail-closed/兼容读取边界。
- [x] 验证：一个 GIS 与一个非 GIS 能力的离线契约；不修改 Runtime 生命周期。

## M327-B：能力选择与用户可见解释

- [x] 让 Planner context 使用有界 descriptor 摘要，而不是固定 workflow 文本。
- [x] 记录 chosen/candidate/missing facts/selection reason 的脱敏 evidence receipt。
- [x] 让澄清、拒绝和不可用结果复用同一选择 identity，不暴露 Prompt 或模型原文。
- [x] 验证：开放请求、缺失事实、未知能力各一条紧凑回归。

## M327-C：跨类型结果摘要

- [x] 冻结 `spatial-agent.result-summary.v1`：Result completeness、typed sections、Evidence、限制、
  `blocks` 和安全 facts 的边界。
- [x] 新增领域中立摘要 projection，将矢量、栅格、指标、时间序列、文本和文档证据映射为统一 block；
  不传播几何、路径、Prompt、模型原文、工具参数或内部引用。
- [x] 将 Composite View 和答案生成 context 接入同一摘要 projection；答案输入优先消费结论、关键发现、
  限制和 evidence 状态，技术 facts 保留在可展开层。
- [x] 验证：至少三类结果的离线 projection 与答案契约（M327-C 专项 `4/4`，受影响紧凑回归 `26/26`，
  答案流相邻回归 `5/5`）。

## M327-D：跨入口与前端接入

- [x] CLI、HTTP、Artifact、恢复和 Console 消费同一 capability/result/evidence projection；同步和恢复响应
  提供同一 `result_summary`，异步完成证据也保留该摘要。
- [x] 前端动态渲染领域中立的结果摘要，保留地图等 Domain View 作为可选 renderer；统一处理对象值，
  不再出现 `[object Object]`。
- [x] 对 planning、clarification、partial、blocked、completed 状态保持同一摘要/证据层级；没有摘要时
  安全降级，不猜测 Domain 语义。
- [x] 验证：Artifact/恢复/异步摘要一致性 `2/2`、M327-C + M326 + M313 紧凑回归 `16/16`、前端
  结构化 projection smoke、Docker compileall 和 architecture strict 通过。

### M327-D 交付边界

- 公共规范来源是嵌套 Result 的 `result_summary`；响应顶层别名和 Artifact 顶层字段只为跨入口读取
  提供便利，不能产生第二套摘要逻辑。
- Console 的公共摘要优先于旧兼容字段；View 只负责地图/图表等可视化，不携带新的 GIS 专用页面分支。
- 摘要前端显示用户可读结论和有界事实，详细运行信息继续位于高级面板；不展示 Prompt、模型原文、
  工具参数、路径、坐标或密钥。

## M327-E：Docker 验收与阶段收口

- [x] Docker 运行受影响紧凑测试、compileall、architecture strict、readiness。
- [x] 进行显式真实模型 + Docker/GIS 开放请求；只记录脱敏成功/失败摘要。
- [x] 更新交接文档、任务账本、中文问题日志和 document/code index。
- [x] 从产品、Runtime、Domain、数据、模型、部署、体验和测试七维度重规划下一阶段并提交推送。

### M327-E 验收记录

- Docker 紧凑回归 `66/66`；readiness `200`；compileall、architecture strict 和 Console projection smoke 通过。
- 真实 Composite 规划：`gis + economic` 两个组件，结构化响应成功；随后异步执行完成，两个组件均完成，结果含
  `composite/vector/metrics` 数据形态，Artifact 和 `spatial-agent.result-summary.v1` 可读取。
- 真实经济数据 + 白名单 Web 搜索：实际执行 `web_search`、`economic_list_indicators`；搜索因公开网络不可达返回
  `search_network_error/unavailable`，本地数据继续完成，未伪造来源；HTTP/Artifact/SSE/Last-Event-ID 对照通过。
- 真实模型工具提案：模型生成纯计算 proposal，经有限 Schema、AST 和 Docker 无网络 sandbox 校验后进入
  `WAITING_FOR_DECISION`；没有执行步骤、没有自动发布，receipt 不含 source/example。
- 真实回答流：两次运行分别产生 `512`、`331` 个 `answer_delta`，均以 terminal event 结束。
- 验收期间未保存 Prompt、模型原文、密钥、网页正文或完整私有结果。

## 风险与验证门槛

| 风险 | 控制 | 验证 |
|---|---|---|
| descriptor 变成新 workflow 硬编码 | descriptor 只描述能力，不携带隐式执行分支 | descriptor/plan identity 契约 |
| 模型选择越权 | 选择后仍过 Registry、策略、权限、审批和 readiness | 负向契约 |
| 结果摘要丢失证据 | 摘要只从 typed Result/Evidence 生成 | 三类结果 projection |
| 前端重新出现 Domain 分支 | 先消费公共 block，再挂载可选 View renderer | Node/browser smoke |
| Provider 不稳定 | 默认离线，真实请求单次、有界超时、脱敏 receipt | Docker/live 验收 |
