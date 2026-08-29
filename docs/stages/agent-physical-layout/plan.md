# Plan：Agent 物理职责归类

> 计划遵循：全局职责盘点 → Spec → Plan → 小批次迁移 → 最小验证 → 更新交接 → 全局重规划。
> 单 Agent 执行，并发度 1；每个批次保持可回滚、可审计和可独立验证。

## P0：冻结基线与迁移清单

- [x] 从 `docs/code-index.json` 读取候选文件、导入和测试映射，生成批次清单。
- [x] 用 `rg` 检查旧路径在生产、脚本、测试和文档中的引用，区分必须保留的公共导入与可迁移内部引用。
- [x] 记录当前工作区已有修改，不覆盖 M323 暂存实现和已有目录迁移。
- 验证：索引校验、架构 strict、`git diff --check`；不运行业务全量测试。

### P0 发现项：Domain 隔离修复

- [x] 将 GIS 专属的 `analysis_ready_binding.py`、`release_evidence.py`、`runtime_capabilities.py` 下沉到 `domains/gis/adapters/`。
- [x] 将 `DemoSpatialAdapter` 下沉为 GIS Adapter，`agent.tools` 只保留惰性兼容导出，不再顶层导入 GIS。
- [x] 更新 GIS Domain、脚本和生产入口使用 canonical adapter；根目录只保留单向 facade。
- 验证：`architecture_check.py --strict` 必须恢复通过，并保留旧路径导入 smoke。

## P1：迁移 Application 支撑实现

- [x] 将 `service_async.py`、`service_format.py`、`service_sessions.py`、`service_state.py` 的 canonical 实现迁入 `agent/application/`。
- [x] 更新 `agent/service.py` 和其他生产调用方，优先引用 `agent.application.*`。
- [x] 根目录保留同名薄兼容 facade，导出集合与旧路径一致；禁止复制实现。
- [x] 更新 code-index override、架构守卫和职责地图，明确 shim 与真实模块。
- 验证：Docker compileall、canonical/legacy import smoke、受影响 service/session contract、architecture strict（通过）。

## P2：迁移 Persistence 实现

- [x] 新增 `agent/persistence/` 包，将 `artifact_access.py`、`artifact_manifest.py`、`artifact_reference.py`、`artifact_store.py`、`artifact_viewer.py`、`memory.py`、`sqlite_store.py` 迁入。
- [x] 收敛 Application、Runtime 和 HTTP 对 canonical persistence 的依赖。
- [x] 根目录保留过渡 facade；更新 compat 分类，确保 `PUBLIC_MODULES` 与 compat 清单不重叠。
- 验证：Docker compileall、SQLite/artifact/restart 紧凑契约、canonical/legacy import smoke、readiness。

### P2 结果

- Docker compileall、`architecture_check.py --strict` 通过；Persistence 紧凑契约 28/28 通过。
- canonical/legacy Persistence import smoke 通过，生产 readiness 返回 HTTP 200。
- 离线 HTTP artifact 测试显式固定为 `rule + memory`，避免继承真实模型产品默认值导致网络超时；生产默认模式未改变。

## P3：迁移 Provider Integration 实现

- [x] 新增 `agent/integration/` 包，将 `openai_config.py`、`provider_runtime.py`、`provider_structured_output.py`、`model_evidence.py` 迁入。
- [x] 更新 Planner、Application 和环境探测的 canonical imports；根路径保留兼容 facade。
- [x] 确保配置读取仍只来自环境/本地配置，不把 key 或模型原文写入索引、日志和交接。
- 验证：Docker compileall、provider config/structured-output 紧凑契约、离线 provider fake smoke；真实模型只在显式验收时运行。

### P3 结果

- Docker compileall、`architecture_check.py --strict`、provider/structured-output/model evidence 定向回归 48/48、canonical/legacy identity smoke 和 readiness 200 通过。
- Provider 生产默认配置仍由环境/本地配置控制；离线测试显式隔离生产 `json_object` 变量，未改变真实模型路径。
- code-index 重新生成 314 个文件，语义覆盖率 100%；根路径四个 Provider 模块被准确标记为兼容 shim。

## P4：全局依赖重规划与第二批决策

- [x] 根据前三批迁移后的导入图重新判断 `result-evidence`、`planning` 和公共契约是否值得继续下沉。
- [x] 将领域中立 Evidence 实现归入 `agent/evidence/`，根目录保留六个单向兼容 facade。
- [x] 确认 `result_registry.py`、`nested_schema.py`、`answer_generation.py`、`planner_*` 和
      `workflow_*` 仍是公共/反向依赖较强的 seam，暂不机械迁移。
- [x] 更新职责地图、架构地图、兼容矩阵、文档索引和阶段交接。
- 验证：Docker compileall、canonical/legacy import smoke、Evidence 紧凑契约、architecture
  strict、code-index/document-index 校验和 readiness；不调用真实模型。

### P4 决策记录

| 候选职责簇 | 决策 | 原因 |
|---|---|---|
| Evidence contract / registry / projection / recovery / revalidation / component | 迁移至 `agent/evidence/` | 领域中立、版本化、只读，调用方集中且可替换收益明确 |
| Result Registry / nested schema / answer generation | 保留现 seam | 与 Domain 注册、Application Composite 和答案生成存在公共或反向依赖 |
| Planner / workflow 实现 | 保留现 seam | 横跨 Planner、Runtime 和 Domain workflow，当前没有低风险深模块 seam |

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 相对导入/绝对导入遗漏 | 先迁移一批；`rg` + canonical/legacy import smoke；不删除 facade |
| 循环依赖因目录变化暴露 | 迁移前读取 code-index 反向依赖；公共契约暂留根目录 |
| dirty worktree 被覆盖 | 只对清单内显式路径操作；每批检查 `git diff --stat` 和 `git diff --check` |
| compat 豁免失真 | shim/facade/真实模块三类单独登记，严格检查不允许重叠 |
| Docker 镜像未包含新路径 | 每个迁移批次后重建镜像再验收 |
