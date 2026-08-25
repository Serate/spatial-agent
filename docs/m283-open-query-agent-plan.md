# Plan: M283 开放式请求 Agent 闭环

## 实施顺序

1. **A 全局规划**：✅ 完成七维度能力图、Spec、Plan；确认复用 M282/M278/M281 契约。
2. **B Planner gateway 收口**：补 Rule/Replay/LLM 的统一输入投影、有限 provider compatibility、plan outcome/repair receipt 和离线回放；不修改 Runtime。
3. **C 开放式成功切片**：用已有 GIS/Economic 能力构造一个不依赖固定问句的 fake/replay 成功 DAG，验证 HTTP、async、artifact、restart 和 planner evidence 一致；真实数据只显式执行。
4. **D 结果体验**：前端消费 context/plan/clarification/evidence 的通用 projection，显示阶段里程碑和可读回答；地图/指标继续按 View 类型动态渲染。
5. **E 真实与跨入口验收**：Docker 重建后执行精简回归、readiness、真实模型/GIS/browser 短验收；成功、澄清、拒绝、Provider 失败分别记录。
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
