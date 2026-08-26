# M308 开放式多组件纵向链路与用户答案质量实施计划

## A：全局基线与 3+ 组件契约

- 以 M306 的真实 2 组件成功链路和 M307 的边界审计为基线。
- 盘点现有能力的输入/输出 profile、readiness、workflow 和结果证据，选择可复用的 3+ 组件组合，不增加新工具。
- 冻结脱敏 replay、合法/非法 DAG、部分失败和答案事实不变的最小契约。

状态：已完成。

- 结果：现有公共 Composite、TaskPlan bridge 和 execution binding 已通过 3+ 组件混合契约；新增 4 项最小回归，修复嵌套 Result answer 未进入 Composite 事实投影的问题，并移除答案上下文中的 request fingerprint。
- Docker 定向验证：4/4 通过；未执行真实模型。

## B：开放组合纵向执行

- 让合法 3+ 组件从 planner canonical request 进入同一个 TaskPlan/DAG、ToolRegistry、workflow 和 execution binding。
- 验证独立组件并行/串行依赖、typed input、缺失事实和有限 repair 的统一状态语义。
- 用真实 Docker 数据确认至少一种混合 data profile 的执行和降级。

状态：已完成。

- 结果：真实 Docker 数据已完成 3 个组件的规划、TaskPlan/DAG、ToolRegistry、workflow、execution binding 与执行；目录能力的 workflow 约束漂移已修复。
- 验证：真实 Docker 组合验收为 `COMPLETED`，GIS、Economic、Indicators 三个组件均完成，混合 profile 为 `composite + vector + raster + metrics`。

## C：结构化事实到用户答案

- 审查 answer generation 的安全事实投影、长度/数值/来源约束和失败 fallback。
- 补充 3+ 组件结果的简洁中文摘要、限制和下一步，不新增工具名或领域专用模板。
- 让 Console 只从 Answer/View/Evidence 投影展示信息层级，详细轨迹保持折叠。

状态：已完成。

- 结果：答案契约保持旧四字段兼容，并增加可选 `next_steps`；公共 fallback 按组合状态生成简短摘要、限制和下一步，Console 已复用既有 `next_steps` 投影。
- 验证：M308 精简契约覆盖答案事实、部分失败限制和下一步投影；未引入领域专用回答模板。

## D：跨入口证据闭合

- 对照 sync、async、HTTP、artifact、SQLite/restart 和 Console 的结果、答案、View、Evidence identity。
- 验证局部失败、数据不可用和答案生成失败不会丢失已完成组件或伪装成成功。

状态：已完成。

- 结果：新增真实 3+ 组件跨入口验收，对照 sync、async、HTTP View、artifact、SQLite 重启的结果、答案、View 和 Evidence identity。
- 验证：跨入口验收中 `sync_async_same`、`http_view_same`、`artifact_view_same`、`evidence_same`、`restart_view_same` 和 `restart_evidence_same` 全部为 `true`。

## E：Docker 阶段验收与必要 live

- 重建并强制重启 Docker，集中运行本阶段精简契约、相邻 Composite 回归、compileall、architecture strict、Node projection、Service smoke、readiness 和 HTTP/artifact/restart acceptance。
- 离线门禁通过且确需验证 provider 3+ 组件行为时，最多执行一次真实模型 + 真实 GIS/Economic；固定 deadline、0 重试，不重复 M306 live。

状态：已完成。

- 结果：在重建后的 Docker 镜像中完成 M308/相邻 Composite 精简回归 **28/28**；真实 GIS/Economic/Indicators 三组件组合与跨入口验收通过。
- 阶段门禁：compileall、architecture strict、Node projection、Service smoke、生产 HTTP acceptance 和 `/health/ready` **200/ready** 均通过；未重复调用 M306 的真实模型验收。

## F：文档、版本和全局重规划

- 更新中文问题日志、milestones、历史恢复卡、快照、任务账本和 README 引用。
- 提交并推送一个阶段版本。
- 从产品、架构、数据、模型、部署、体验、测试七个维度规划下一阶段，继续避免陷入单一数据集细节。

状态：已完成。

- 结果：中文问题日志、milestones、恢复快照和任务账本已同步；M309 已从项目全局规划为“真实模型开放组合与默认 Agent 体验”。本阶段不保存密钥、prompt、模型原文、完整原始数据或私有路径。
- 交付：待本次工作区统一提交并推送 M308 阶段版本。

## 交付顺序

`A → B → C → D → E → F`

开发期间只做必要静态/契约检查；A～D 合并后集中运行 E，测试轮次按独立失败模式合并。
