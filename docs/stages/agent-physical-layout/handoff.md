# Agent 物理职责归类交接

## 当前状态

- 阶段：P0/P1/P2/P3/P4 已完成，物理职责归类阶段收口。
- M323：按用户要求暂停，不收口人工审批实现。
- Application 支撑、GIS Domain 隔离、Persistence、Provider Integration 和 Evidence 迁移已完成；根目录仍保留单向兼容 facade。

## 已完成

- `agent/` 168 个源码文件已完成职责地图，语义覆盖率 100%。
- 依赖审计确认根目录包含公共 seam、兼容 facade 和实现型模块，不能整体机械搬迁。
- 首批方案确定为 Application 支撑、Persistence、Provider Integration，公共契约暂留根目录。
- P2 已将 Artifact、Memory、SQLite 实现归入 `agent/persistence/`，生产调用已切换 canonical 路径。
- P2 Docker compileall、architecture strict、Persistence 28/28 紧凑契约、canonical/legacy import smoke 和 readiness 200 全部通过。
- P3 已将 Provider config、structured output、runtime evidence、model evidence 归入 `agent/integration/`；生产调用已切换 canonical 路径。
- P3 Docker compileall、architecture strict、Provider 定向回归 48/48、canonical/legacy identity smoke 和 readiness 200 全部通过。
- P4 全局依赖审计确认 Evidence 具有独立 canonical seam，已迁移到 `agent/evidence/`；Result、Planning
  和 Answer Generation 暂留公共 seam，避免反向依赖和机械拆分。
- P4 文档已同步：架构地图、兼容矩阵、code-index、document-index、Plan、热状态和任务账本。

## P4 已执行

1. 审计 P0～P3 后的依赖图、调用方和循环风险。
2. 建立 `agent/evidence/` canonical package，生产导入切换到 canonical seam。
3. 保留六个根目录 Evidence 兼容 facade，并验证 canonical/legacy identity。
4. 更新索引、职责地图、架构地图、兼容矩阵和恢复交接。

## 阶段门禁结果

- Docker compileall：通过。
- `architecture_check.py --strict`：通过；仅保留既有 Runtime/Service God module warning，无 error。
- Evidence 定向契约：23/23 通过。
- canonical/legacy identity smoke：通过。
- code-index：321/321，语义覆盖率 100%。
- document-index：通过；readiness：HTTP 200。

## 下一步

1. 物理职责归类阶段可交付；由全局规划决定是否恢复 M323。
2. 在用户明确恢复前不继续 M323 人工审批实现。
3. 不为 Result/Planner 做机械物理拆分；只有出现独立替换需求和稳定 seam 时再单独立项。

## 必要文件

- `docs/agent-work-state.md`
- `tasks/current-state.md`
- `docs/stages/agent-physical-layout/handoff.md`
- `docs/stages/agent-physical-layout/plan.md`
- `docs/architecture-map.md`
- `docs/compatibility-matrix.md`
- `docs/code-index.json`
- `docs/code-index-overrides.json`
- `agent/evidence/`
- `agent/evidence_contract.py`
- `agent/evidence_projection.py`
- `agent/evidence_recovery.py`
- `agent/evidence_registry.py`
- `agent/evidence_revalidation.py`
- `agent/component_evidence.py`
- `scripts/architecture_check.py`
- `scripts/validate_code_index.ps1`
- `scripts/validate_document_index.ps1`

## 不变量

- canonical 实现只能有一份。
- 根目录兼容入口只能单向导出，不新增行为。
- 不改变 Runtime、ToolRegistry、Result/Evidence、Artifact/SQLite/restart 和 HTTP 语义。
