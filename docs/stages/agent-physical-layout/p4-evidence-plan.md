# P4 Evidence 物理归类 Plan

## 批次

1. 建立 `agent/evidence/` lazy package，迁移六个领域中立实现。
2. 调整 canonical 内部导入和 Application/Runtime/Domain 调用方；根目录只保留 facade。
3. 更新 architecture compat、code-index override、职责地图和兼容矩阵。
4. 在 Docker 中运行 compileall、严格架构检查、evidence/恢复紧凑契约和 readiness。
5. 更新阶段交接与任务账本；若门禁通过，结束物理归类阶段，不继续机械拆分 result/planner。

## 失败恢复

- 任一 import/cycle 失败时，停止后续移动，仅修复当前 batch 的 import seam。
- 不回滚用户既有 dirty changes，不删除兼容 facade。
- 不调用真实模型；provider/live 验收不属于本批次风险。
