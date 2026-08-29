# P4 Evidence 物理归类 Spec

## 背景

P0～P3 已将 Application、Persistence、GIS Adapter 和 Provider Integration 归入
canonical 目录。P4 全局依赖审计显示，`agent/evidence_*.py` 与
`agent/component_evidence.py` 形成领域中立、只读、有版本的证据投影组，根目录实现已
主要承担历史导入入口；这组能力适合独立物理归类。

## 范围

- canonical：`agent/evidence/contract.py`、`projection.py`、`recovery.py`、
  `registry.py`、`revalidation.py`、`component.py`。
- 根目录保留同名兼容 facade，旧导入继续可用且只单向转发。
- 生产代码改用 `agent.evidence.*`；不改变 Evidence schema、字段限幅、恢复语义或
  Domain Pack 边界。

## 明确不做

- `result_registry.py`、`nested_schema.py`、`answer_generation.py` 不迁移：它们分别与
  Domain 注册、Application Composite 和答案生成存在公共/反向依赖。
- `planner_*`、`workflow_*` 不整体迁移：它们横跨 Planner、Runtime 和 Domain workflow，
  当前没有一个低风险 canonical seam。
- 不删除根入口，不修改 Runtime 生命周期、HTTP 契约、ToolRegistry 或模型调用。

## 不变量与验收

1. canonical 与 legacy import 输出符号一致，且只存在一份实现。
2. 所有现有 evidence 投影、异步/SQLite/artifact 恢复路径保持同一 JSON 结果。
3. Docker compileall、architecture strict、evidence 相关紧凑契约和 readiness 通过。
4. code-index 与职责地图准确标记 canonical evidence 和兼容 facade，语义覆盖率保持 100%。
