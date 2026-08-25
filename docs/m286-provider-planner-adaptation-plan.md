# M286 中转模型 Planner 适配 Plan

## 实施顺序

1. **A 全局盘点与契约冻结**：完成能力图/Spec，确认 M285 的 TaskPlan bridge、allowlist、Result/Evidence 和生命周期边界不变。
2. **B Context identity projection**：为候选能力增加领域中立的精确身份提示、工具/结果摘要和预算回归；不增加授权字段之外的敏感数据。
3. **C Provider adapter 收敛**：对已有正常化器补充有证据的有限 wrapper/别名兼容；所有未知字段、冲突字段和非法状态继续 fail closed。
4. **D Failure/application integration**：统一 provider/context/schema/allowlist/TaskPlan policy 错误摘要，接通现有 repair lineage 和跨入口 projection；不改变 Runtime 执行循环。
5. **E 精简验收与交付**：集中运行 M286 contract、M285/M283 相邻回归、compileall、architecture strict、readiness；最后单次真实 live probe，更新中文记录并推送。

## 文件边界

- B：`agent/composite_request_context.py`、`agent/composite_planner.py`、对应最小 contract 测试。
- C/D：`agent/composite_planner.py`、`agent/application/composite_planning.py`、必要的通用 projection/evidence 文件。
- E：`docs/*`、`tasks/*`、中文问题日志和部署/验收脚本；不修改 GIS/Economic 算法。

## 测试节奏

- 开发中只运行语法/导入或当前独立失败模式的最小检查。
- 相关实现完成后集中运行一组 M286 contract；不为每个子任务重复跑 M285 全套。
- 阶段收口运行一次 M286 + 相邻 M285/M283 精简回归、Docker 编译/架构/readiness 和一次显式 live probe。
- 不把真实 live、浏览器或完整回归加入默认 CI。

## 风险控制

- 模型仍选错能力：增加精确身份提示，但本地 allowlist 不放宽；继续返回 `capability_not_registered`。
- provider 继续输出未知包装：只增加有文档且可回放的 adapter 映射，否则拒绝。
- context 变大：保持 byte budget 和字段白名单，优先裁剪描述，不裁剪身份/工具/结果契约。
- 跨入口漂移：复用已有 canonical result/evidence 和 `CompositeRunApplication`，不在 transport 重建状态机。
