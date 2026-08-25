# Plan: M283 开放式请求 Agent 闭环

## 实施顺序

1. **A 全局规划**：✅ 完成七维度能力图、Spec、Plan；确认复用 M282/M278/M281 契约。
2. **B Planner gateway 收口**：补 Rule/Replay/LLM 的统一输入投影、有限 provider compatibility、plan outcome/repair receipt 和离线回放；不修改 Runtime。
3. **C 开放式成功切片**：用已有 GIS/Economic 能力构造一个不依赖固定问句的 fake/replay 成功 DAG，验证 HTTP、async、artifact、restart 和 planner evidence 一致；真实数据只显式执行。
4. **D 结果体验**：✅ 前端消费 context/plan/clarification/evidence 的通用 projection，显示阶段里程碑和可读回答；地图/指标继续按 View 类型动态渲染。
5. **E 真实与跨入口验收**：✅ Docker 重建后执行精简回归、readiness、真实模型/GIS/browser 短验收；成功、澄清、拒绝、Provider 失败分别记录。
6. **F 收口与重规划**：更新中文问题日志、milestones、恢复快照和任务账本，提交推送版本，再按七维度规划下一阶段。

## 风险控制

- Provider 字段漂移：只增加可枚举、可测试的别名；未知字段 fail closed。
- 开放问题过度澄清：优先使用 Domain 声明的唯一候选/事实，不在公共层添加专题关键词。
- 前端重复编排：只消费 Projection，不自行判断 Domain、工具名或运行状态。
- 测试膨胀：保留一条正向、一条澄清、一条拒绝、一条恢复和一条显式 live 验收；删除无独立失败模式的重复调用。
- 环境误判：Docker 镜像每次源码/测试变更后重建；Provider 失败不写成代码通过。

## Verification checkpoints

- B：Planner gateway fake/replay contract、schema/allowlist/repair tests。
- C：Composite lifecycle/HTTP/async/artifact/restart 的最小成功切片。
- D：前端 context/plan/answer/view/evidence renderer smoke。
- E：Docker readiness、真实 GIS、真实模型和 browser 显式 receipt。
- F：阶段文档、版本推送和全局重规划。

## M283-D 交付记录

- 新增 `ConsoleResultProjection`，从版本化 Composite View、runtime context、plan、clarification 和 evidence 生成有界用户投影。
- 结论区现在按“分析阶段 → 结果摘要 → 关键发现 → 使用边界/下一步”展示；DAG、工具执行轨迹和详细证据仍在折叠的高级区域，不把内部思维过程呈现给用户。
- 前端 projection 不依赖 GIS、Economic、区域名或工具名；未知结果类型仍使用通用空态和 View renderer。
- 静态资源通过 `agent/web_assets.py` 的公共 allowlist 提供，避免 FastAPI/stdlib 入口出现资源分叉。
- 验证：Node projection smoke、Docker 内 Node projection smoke、生产 `/health/ready` 200、资源 200、浏览器 projection smoke 通过；已有地图 smoke 暴露一个与本次 projection 无关的旧问题：清空对话后地图选择上下文未立即复位，已记录到中文问题日志，未将其误报为本阶段通过。

## M283-E 交付记录

- Docker 重建后 M283 Planner/evidence contract **7/7**、compileall 和 architecture strict 通过，生产 `/health/ready` 与新静态资源均返回 200。
- Node projection smoke、Docker 内 projection smoke 和浏览器 projection smoke 通过；浏览器验证 6 个阶段、关键发现和隐藏工具名不出现在用户投影中。
- 真实模型 + local GIS 显式短验收 `live-gis-spatial-overview`：1 次请求、0 重试、`COMPLETED`，真实执行成功；只保留脱敏摘要，未保存 prompt、模型原文或密钥。该请求约 8,028 tokens、42.5 秒，仅作为手工 live receipt，不进入默认 CI。
- 既有地图 smoke 仍暴露清空对话后空间上下文未立即复位，已独立记录，不阻塞本阶段结果 projection 合同。
