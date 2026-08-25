# M294 已验证计划到执行/答案/证据闭合 Plan

本阶段依据 [`docs/m294-planned-execution-result-closure-capability-map.md`](m294-planned-execution-result-closure-capability-map.md) 和 [`docs/m294-planned-execution-result-closure-spec.md`](m294-planned-execution-result-closure-spec.md) 执行。

## 完整能力包（串行）

### M294-A：计划—执行 binding 契约

- 从现有 TaskPlan bridge、DAG、capability allowlist 和 completeness receipt 生成版本化 execution binding。
- 计算稳定 plan fingerprint，绑定 request/component/step/tool/result type；不携带模型原文或私有实现。
- 明确 binding 创建、验证、拒绝和用户可读错误状态，保持 Runtime/ToolRegistry 单一门禁。

### M294-B：Composite coordinator 消费 binding

- submit/run/async 只把已验证 binding 交给 coordinator，禁止再次从 canonical request 猜测组件步骤。
- 将 binding 的组件和步骤 identity 贯穿 ToolRegistry dispatch、Domain Result 和失败/部分完成 lineage。
- 对旧入口提供 bounded compatibility projection，但不能允许旧入口绕过 binding。

### M294-C：答案、View 和 Evidence 闭合

- 让 Result/View/Artifact/Evidence 引用同一 plan fingerprint 和组件/步骤摘要。
- 统一结构化答案输入：真实事实、限制、来源、降级状态；回答模型失败时使用可读 fallback，不暴露内部格式。
- 前端结论优先显示答案和关键发现，轨迹/计划/evidence 作为渐进详情，不增加领域页面分支。

### M294-D：同步/异步/重启与真实数据验收

- 用一个 compact contract 覆盖 binding 成功、篡改/漂移拒绝、同步/异步 evidence parity 和答案 fallback。
- Docker 重建后统一运行 M294 + M293/M291 相邻回归、compileall、architecture、readiness；按需执行一次真实 GIS 或 Economic 数据验收。
- 记录 Planner、binding、执行、数据后端和答案生成的独立错误分类；不重复昂贵 live 请求。

### M294-E：阶段交付与全局重规划

- 更新中文问题日志、milestones、恢复账本、任务清单和上下文归档。
- 提交并推送版本，分别记录本地 commit 与远端 push。
- 从产品、架构、数据、模型、部署、体验、测试七个维度规划下一阶段，确认是否进入更通用的工具组合或数据发现能力。

## 依赖与风险

- A 必须先固定 binding identity，B 才能替换执行输入；C 依赖真实结果边界，D 再验证恢复一致性。
- 旧 Composite coordinator 可能只理解 canonical request：采用显式 adapter 接收 binding，迁移完成前 fail closed，不双写第二套编排循环。
- 答案生成不能用模板掩盖事实缺失；所有 fallback 必须保留限制和来源。

## 验证节奏

A～C 集中实现后只运行一次 compact contract；D 阶段运行一次合并门禁和必要的显式 live。测试数量以独立失败模式为上限，不随任务数量线性增加。
