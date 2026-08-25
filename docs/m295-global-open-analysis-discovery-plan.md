# M295 全局开放式分析与数据发现实施计划

本阶段按一个完整能力包串行实施，任务数量覆盖连续依赖，测试集中到阶段收口。

## M295-A：全局基线与契约冻结

- 对产品、架构、数据、模型、部署、体验、测试七个维度做缺口盘点。
- 盘点现有 RequestFacts、Capability Catalog、Domain discovery/readiness、clarification continuation 和 M294 execution binding，决定复用点和唯一新 seam。
- 固定 discovery receipt 的 schema、fingerprint、reason code、预算和安全投影。
- 更新恢复账本和任务清单，明确待修改源码/测试文件。

## M295-B：领域中立 Discovery Gateway

- 新增 discovery gateway 深模块，聚合 Domain Pack 的事实、能力目录、数据目录和 readiness。
- 生成 bounded capability candidates、data requirements、source evidence、缺失事实和可恢复建议。
- 加入 request/discovery identity 校验，拒绝未注册 Domain、超预算字段和敏感内容。
- 保持 Domain 专属数据判断在 Domain Pack 内，公共层只消费契约。

## M295-C：Planner 与生命周期集成

- Rule/Replay/LLM 共用 discovery receipt，规划前先执行 capability/data match。
- 把 discovery 状态接入 clarify → plan → validate/repair → binding → execute 生命周期。
- 复用 M294 binding，不新增第二套 coordinator 或执行循环。
- 保持 continuation 的组件集合和 request fingerprint 校验。

## M295-D：结果与前端渐进展示

- 将 discovery/readiness/source evidence 投影到 Result/View/Evidence/Artifact。
- 前端按结构化状态显示“需要补充、数据不可用、已规划、已完成、部分完成”，不按领域或工具名分支。
- 对开放问题提供关键发现、限制和下一步动作，内部计划作为可展开详情。

## M295-E：跨领域数据与显式验收

- 使用已有真实 GIS 数据和可追溯 Economic 数据做一条跨领域成功/澄清/不可用对照。
- 验收同步、异步、SQLite/artifact restart 的 identity parity；不保存模型原文或敏感配置。
- 统一运行 discovery compact contract、相邻 M294 回归、compileall、architecture strict、readiness 和必要的 Node/HTTP smoke。

## M295-F：阶段交付与全局重规划

- 更新中文 `docs/agent-development-issues.md`、任务账本、工作快照和 milestones。
- 提交并推送阶段版本，记录 commit、push 和验证证据。
- 从七个维度重新评估是否进入通用算子组合、Economic Domain 完整数据链路或真实模型体验，不按单个数据细节决定下一阶段。

## 验证节奏

实现期间只做必要的语法/局部检查；M295-B～D 完成后集中运行一个 compact contract 和相邻回归；M295-E 统一执行 Docker、架构、readiness、HTTP/Node 和一次显式 live。测试数量以独立失败模式为上限。
