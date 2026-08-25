# M262 架构收敛 Spec

状态：已完成

## 目标

继续把 Agent Runtime 从“能运行的组合入口”收敛为可测试、可观测、可替换的深模块，解决当前重构中最后三类明显结构债务：

1. `RuntimeRunLifecycle.run()` 的阶段职责仍集中在一个大方法中。
2. FastAPI 与标准库 HTTP 入口仍各自维护传输层胶水。
3. 架构守卫把真实公共模块和兼容入口混在同一个豁免清单中。

GIS、Text、Indicators 的业务行为、公共 HTTP 路径、Result/Evidence/Artifact schema 和旧导入路径必须保持兼容。

## 设计原则

- Runtime 只编排阶段，不携带 Domain 策略。
- 阶段之间通过一个内部 `LifecycleContext` 传递状态，不通过隐式模块全局变量传递。
- 阶段是 Runtime 内部 seam，不扩大公共 API；旧 `AgentRuntime.run()` 签名保持不变。
- HTTP 语义继续由 `agent.application.http.HTTPApplication` 单源负责。
- FastAPI 与 stdlib 只负责框架适配，公共请求解析、响应编码、错误映射和 artifact 安全访问使用共享 transport module。
- 兼容入口只能单向委托；真实公共模块不得因为历史 fallback 获得架构守卫豁免。
- 不以减少行数为唯一目标，优先保证阶段职责、依赖注入和行为可验证。

## 生命周期阶段接口

### resolve

输入：原始请求、session、超时、决策参数和可选 resolved request。

输出：`ResolvedRun`，至少包含 pending turn、resolved request、RequestFacts、run id、deadline，以及 decision resume 信息。

不变量：不创建工具步骤、不调用 ToolRegistry；decision resume 仍能定位原运行。

### clarify

输入：`ResolvedRun`。

输出：包含 Result、context packet 和初始持久化状态的 `LifecycleContext`。

不变量：保持 conversation turn、domain/runtime context、request facts、context evidence 和初始 `PLANNING` 状态的原有形状。

### plan

输入：`LifecycleContext`。

输出：候选 `TaskPlan`。

不变量：保留 workflow selection、Planner metrics 和 planner selection evidence；不执行工具。

### validate / repair

输入：候选计划和生命周期上下文。

输出：可执行计划或结构化澄清/拒绝/失败。

不变量：复用现有 validation、repair lineage、plan identity、evidence binding 和 fingerprint gate；规划修复预算不改变。

### execute

输入：已验证计划和生命周期上下文。

输出：步骤状态、工具结果、execution replan lineage。

不变量：所有工具仍经过既有 Runtime/ToolRegistry seam；取消、超时、有限重规划和 blocked steps 的行为不变。

### answer

输入：执行结果或 direct-answer 计划。

输出：用户可读 answer 和 answer evidence。

不变量：继续使用真实模型回答生成和 Domain fallback；不把内部步骤列表直接当作用户回答。

### evidence / finalize

输入：生命周期上下文和异常（如有）。

输出：最终 Result、状态保存、终态事件。

不变量：Clarification、Rejected、Cancelled、Timed out、Failed、Completed、Waiting for decision 均保留原有状态、failure phase、plan evidence 和 artifact/SQLite 可恢复性。

## Transport seam

新增共享传输辅助模块，至少提供：

- URL/path/query 的标准化读取。
- JSON body 解码和 UTF-8 JSON 响应编码。
- 统一异常到 status/error envelope 的映射。
- 安全 artifact 定位、artifact JSON 读取和 manifest/evidence 投影辅助。

FastAPI 和 stdlib 入口仍可保留各自的 route declaration、`BaseHTTPRequestHandler` 和 FastAPI response 类型，但不得复制上述语义。

## 架构守卫清单

将旧的 `COMPAT_MODULES` 拆为：

- `COMPAT_SHIMS`：真正只做历史导出的简单 shim。
- `COMPAT_FACADES`：仍需兼容旧调用、但内部可能包含有限适配逻辑的入口。
- 真实公共模块：`domain_contract`、`workflow_templates`、`domain_registry`、`result_registry` 等，不进入豁免集合。

守卫报告必须同时输出 shim/facade 清单，并验证真实公共模块不会被兼容豁免覆盖。当前守卫仍以顶层导入检查为主；本阶段先完成清单语义纠正，递归导入检查作为后续独立收敛项，避免把历史 lazy fallback 与本阶段生命周期改动混在一起。

## 兼容与验收

- `AgentRuntime.run()`、`AgentService.run()`、CLI、HTTP、async、SQLite/artifact recovery 的公共结果契约不变。
- 至少覆盖普通完成、澄清、失败/拒绝、decision waiting/resume 四条生命周期路径。
- 默认验证保持精简；Docker 中执行 compileall、architecture strict、quick 和本阶段定向契约。
- 不调用真实模型、不写入私有数据、不提交密钥；真实模型/GIS 继续作为显式验收路径。
