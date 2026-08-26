# M302 分阶段 Planner 上下文与开放问题成功链路实施计划

## A：全局基线与阶段字段矩阵

- 盘点现有 Planner Envelope、selection evidence、component fact handoff、TaskPlan bridge 和答案生成调用点。
- 冻结四类 projection stage 的必需字段、可选字段、预算和失败状态。
- 建立一个代表性开放请求矩阵，覆盖成功、无关事实缺失、选中组件缺事实、不可用数据和 provider failure。

## B：阶段感知 Envelope

- 在公共 Runtime 增加 stage-aware projection seam；保留现有默认 Envelope 兼容读取。
- 把仅供 Runtime 诊断的完整 discovery/consistency 明细留在内部 evidence，不默认发给模型。
- 为每个阶段增加最小预算测量和私有字段过滤，超限 fail closed。

## C：选择到执行的纵向闭合

- 让 LLM/Rule/Replay 经过同一候选选择、组件事实交接、TaskPlan/DAG 和 binding 门禁。
- 对选中组件缺事实生成有界 continuation，补充后只重建必要上下文。
- 验证不相关 Domain 缺事实不会改变合法候选的执行路径。

## D：结果答案与前端投影

- 统一结构化结果、evidence 和答案引用，减少程序化模板摘要。
- 前端按阶段和结果类型展示用户可读信息，详细技术证据默认折叠。
- 保持未知结果类型和 provider failure 的通用降级，不增加领域页面分支。

## E：集中验收与交付

- Docker 集中运行阶段 contract、生命周期/binding 回归、compileall、architecture strict、Node projection 和 readiness。
- 只做一次显式 live 验收，记录脱敏状态、请求次数、重试次数、是否创建 run 和错误分类。
- 更新中文问题日志、milestones、任务账本、恢复快照和部署记忆，提交并推送阶段版本。
- 以产品、架构、数据、模型、部署、体验、测试七维度重新规划下一阶段。

## 风险控制

- 阶段投影不能成为第二套生命周期；所有执行仍由现有 binding 门禁授权。
- 为节省 token 不能删除候选 identity、事实缺口、readiness、workflow 或 result profile 等决策必需字段。
- 真实模型不稳定时记录 provider failure，不放宽 schema、不增加无界重试。

## 当前进度

- A/B 已完成：Envelope 声明并校验四类阶段；Context Builder 保存 discovery 投影；LLM 初次规划/一次结构修复分别使用 selection/repair；execution 与已有 selected component 只保留选中闭合信息。
- C 已完成：execution projection 在 TaskPlan/DAG、plan completeness 和 execution binding 全部门禁通过后生成；execution binding 纳入 capability identity，plan fingerprint 覆盖 capability（兼容旧 binding 的可选字段）；projection 校验组件集合、顺序、领域、能力、依赖和 required identity；`execution_identity` 纳入 Envelope 安全规范化，evidence 只保留有界 receipt。
- 已验证：阶段切换不改变 request fingerprint；readiness、workflow、result profile 和私有字段过滤保持；已有 Envelope 可安全规范化；repair 在尚未形成可信选中项时保留有界候选以支持一次结构修复。
- C 验证：Docker M302-C 与 M294/M293/M292 **19/19**；compileall、architecture strict、Service smoke 和生产 readiness HTTP **200** 通过；新镜像已重建并强制接管，避免旧容器假绿灯。
- D 已完成：Composite View 透传安全的答案生成 evidence，损坏计数字段统一安全归一化；结果契约确保 Registry 声明的 ViewSpec 同时登记到 workspace，未知/不可用视图由公共 fallback 表达，前端只消费结构化 evidence。
- D 验证：新增结果投影与 workspace/View 闭合契约；修复前最小用例稳定失败，修复后通过，未增加 GIS 专用分支。
- E 已完成：在重建后的 Docker 镜像中集中执行 M302/答案/Composite 精简回归 **26/26**、compileall、architecture strict、Service smoke、Node projection smoke；生产 HTTP/异步/artifact/restart 验收通过，`/health/ready` 返回 **200**。
- E 显式 live：真实中转结构化输出通道可达，单次请求、0 重试、约 47 秒后返回 `NEEDS_CLARIFICATION`，未创建 execution run；按 provider/语义澄清分类记录，不伪装成跨域成功。
- 阶段结论：M302-D/E 已完成，Result → answer/evidence → View/Console 的公共事实链路和跨入口契约已收口；下一步按七维度全局重规划开放式 LLM Composite 成功执行能力。
