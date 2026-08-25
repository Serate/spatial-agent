# M269 Plan：通用记录分析能力

## 实施原则

按 `Spec → 实现 → Docker 验收 → 全局重规划` 串行推进。每一步先保留旧工具契约，再通过新深模块收敛重复逻辑；不修改 Runtime 主循环和 Planner 生命周期。

## 任务

### 1. 建立核心接口与契约

- [x] 新增 `agent/analysis/record_contract.py`，定义操作、聚合函数、稳定错误 code、预算和 JSON-safe 规范化。
  - 验收：非法操作、未知聚合、缺字段和预算均有稳定结构化结果。
  - 验证：M269 核心 contract 单测。
- [x] 新增 `agent/analysis/record_analysis.py`，实现 filter、aggregate、timeseries、compare。
  - 验收：不导入 Domain、无 I/O、同一接口支持 mapping records。
  - 验证：核心单测覆盖正常/空集/缺字段/边界。

### 2. 收敛指标核心

- [x] 让 `IndicatorAnalysisEngine` 复用通用 filter、分组和排序实现，保留现有 latest/trend/compare/source evidence 输出兼容；期间筛选保留 Indicator Domain 的 period key 语义。
  - 验收：Economic/Indicators 旧结果类型、来源证据和状态码不变。
  - 验证：M251/M263/M264 定向回归。

### 3. 接入 GIS 文件型记录分析

- [x] 在 GIS 文件适配器中增加有界属性记录投影和 `record_analysis` 调用，不返回 geometry 到通用 rows。
  - 验收：`earthquakes_wuhan` 等 Catalog-ready vector 可按字段过滤/聚合。
- [x] 在 ToolRegistry schema、GIS catalog/workflow/result registry/view 中登记通用工具和 result type。
  - 验收：Planner 只能看到已注册工具；未知 dataset/field 进入 preflight/structured failure。
- [x] 保持 `range_query` 和 `earthquake_event_query` 兼容；不增加地震名称分支。

### 4. 跨领域结果与用户体验接线

- [x] 三个 Domain 登记 `record_analysis_result` 的 data profile 与 generic View。
- [x] 让 GIS/Economic/Indicators View 使用结构化 rows/metrics 生成表格、指标卡和趋势点，详细步骤留在 evidence；不输出内部思维链。
- [x] 前端仅依据 Result/View/evidence 动态渲染表格、指标或趋势，不判断 `earthquake`、`economic` 等专题名称。

### 5. 验收与文档

- [x] 新增一个精简 M269 测试模块，避免复制旧测试矩阵；Adapter contract 合并到相邻 M268 测试。
- [x] Docker 执行 M269 定向回归、相邻 Economic/Indicators/GIS contract、compileall、architecture strict、quick/stage。
- [x] 使用真实经济数据与一次性挂载真实地震数据做跨领域验收；只记录数据状态、结果类型和核心统计，不记录原始数据/密钥/宿主绝对路径。
- [x] 更新 `docs/agent-context-resume.md`、`docs/agent-development-issues.md`、`docs/milestones.md`，完成敏感检查后 commit/push。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 通用核心变成把所有领域语义塞进一个大接口 | 只接受 mapping records 和显式字段；领域解释留在 Adapter/Planner guidance |
| GIS geometry 或路径泄漏到记录结果 | Provider 先做属性投影；核心再做敏感键、深度和行数预算 |
| 旧 Economic 结果契约漂移 | 先保留 `IndicatorAnalysisEngine` facade，新增 contract 对比旧结果 |
| 模型选择未注册字段/工具 | ToolRegistry schema、Domain preflight 和执行前字段校验三重门禁 |
| 真实数据挂载误判 | 一次性只读挂载，分别记录 host/container/catalog/provider 四层证据 |
| 前端再次出现领域专用分支 | 只扩展 Result Registry/View metadata 和 renderer registry |

## 收口门禁

只有以下条件全部满足才结束 M269：

1. Spec、Plan、Map 与实现一致。
2. 核心与 Provider 测试在 Docker 通过。
3. Economic 与 GIS 真实数据都证明共享核心。
4. Runtime、ToolRegistry、HTTP、Artifact、Evidence 和前端主流程没有专题分支。
5. 默认 CI 保持离线精简，live 验收显式记录。
