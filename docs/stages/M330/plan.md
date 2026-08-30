# Plan：M330 通用 Agent 开放问题质量与纵向行为验收

> 顺序：全局能力图 → Spec → 行为基线 → 答案与体验 → 跨入口恢复 → Docker/live 验收 → 交接/提交/全局重规划。
> 单 Agent，最大并发度 1；测试采用最小充分原则。

## M330-0：阶段初始化

- [x] 建立 capability map、Spec、Plan、handoff。
- [x] 将恢复入口切换到 M330，只保留热状态、handoff 和必要源码。
- [x] 固定场景矩阵、预期 request mode、Result kind、evidence 状态和用户答案要求。

## M330-A：通用直接回答

- [x] 选取概念解释、比较、总结、写作和简单计算等非 GIS/经济问题，确认无需关键词即可得到答案。
- [x] 答案生成允许不依赖外部数据的通用请求使用请求本身；模型答案保持结论优先、自然中文和安全边界，不暴露内部状态、
  工具名、Prompt 或思维链。
- [x] 检查模型不可用时的领域中立 fallback，区分离线限制与“没有结果”。
- [x] Docker 紧凑契约测试覆盖场景矩阵、`request_mode`、空工具步骤和答案 evidence。

## M330-B：开放请求与能力发现

- [x] 验证单域和跨域请求由 Capability Catalog + ReAct 选择工具，不添加固定问句分支。
- [x] 验证缺少关键事实时只澄清必要字段；未知但可直接回答的问题不被能力目录误拒绝。
- [x] 验证多个结果类型能够汇总为统一 Result Summary，保留 owner、限制和证据来源。
- [x] 验证已登记工具参数、依赖、权限、预算和结果 schema 在执行前完整校验。
- [x] 增加公共工具操作到结果类型的受控推导；可信目录优先于模型标签，歧义和未知类型保持 fail-closed。

## M330-C：开放行动与故障恢复

- [x] 验证白名单 Web 的成功、无结果、网络失败和重定向失败均可读且不伪造来源。
- [x] 验证工具提案经过 sandbox、人工审批、同一 Run 恢复；拒绝/过期/撤销不执行。
- [x] 验证 provider 部分不可用时仍可直接回答或保留其他 Domain 结果，并明确 degraded 限制。
- [x] 验证取消、重试、有限修复、澄清续跑的状态和 lineage 可读。
- [x] Docker 紧凑回归和显式提案验收通过；live provider 延迟按脱敏边界记录。

## M330-D：实时产品体验

- [x] 校验 RunEvent 阶段、当前动作、耗时、心跳、答案 delta 和终态在 CLI/HTTP/前端一致。
- [x] 校验 SSE 断线重连、Last-Event-ID、轮询降级和 Artifact 回放不重复、不丢终态。
- [x] 校验前端默认突出结论和结构化结果，过程/证据/地图按类型动态展示，不新增 Domain 页面分支。
- [x] 校验答案流发生 provider 降级时仍有明确结束状态和可恢复操作。

## M330-E：阶段验收

- [x] Docker 运行一个合并后的紧凑契约模块和必要相邻回归，不按场景重复全量测试。
- [x] Docker compileall、architecture strict、code/document index、readiness 和前端 smoke。
- [x] 真实模型完成非数据、单域/跨域、Web/降级、提案/审批、多轮续问至少各一条代表性验收。
- [x] 只记录脱敏状态、动作计数、结果类型、evidence 和事件序列，不记录模型原文或私密数据。

## M330-F：交付与全局重规划

- [x] 更新 `docs/agent-work-state.md`、`tasks/current-state.md`、`tasks/task-progress.md` 和 M330 handoff。
- [x] 更新 code/document index，提交并推送阶段版本。
- [x] 从产品、Runtime、Planner、Domain、数据、模型、部署、体验和测试全局规划下一阶段。
