# M265 数据就绪事实进入 Planner Context Plan

状态：已完成

## 任务

### 1. Runtime evidence projection

- [x] 将 `DatasetCatalog` discovery 字段安全并入 GIS `data_evidence`。
  - 验收：只出现 stage/status/coverage/time_range/crs/resolution/source_url/availability_reason 等白名单字段。
  - 验证：M265 projection contract。

### 2. Planner projection

- [x] 在 `capability_context_summary` 中按 selected capability 的 datasets 投影 `dataset_evidence`。
- [x] 在 `planner_context.py` 传播该字段并保持 bounded budget。
  - 验收：模型上下文看到数据事实但看不到路径和大报告；未选中数据不泄漏。
  - 验证：M265 context contract、M249 open planner context。

### 3. Cross-domain regression

- [x] 回归 GIS、Economic、Indicators、Text 的 context、Result、HTTP 和 artifact 兼容。
- [x] 显式抽查真实 GIS snapshot 与真实 Economic HTTP；不新增专题分支。

### 4. 收口

- [x] 更新中文恢复卡、milestones、问题日志。
- [x] Docker compileall、architecture strict、quick/stage、diff check、commit/push。
- [x] 按七个全局维度重新决定下一阶段是第三专题验收还是 workflow/catalog 工厂化。

## Completion evidence

- 定向回归 14/14；stage、quick、compileall、architecture strict 和真实 GIS capability snapshot 均通过。
- 原错误测试模块名 `tests.test_m249_open_planner_context` 已修正为实际模块 `tests.test_m249_open_planner`。
- 下一阶段选择先做“声明式 Domain/Capability Pack 接入工厂”的小切片，再以第三个指标类专题或真实扩展数据验收新增成本；不复制 Runtime 生命周期，也不提前引入 RAG。

## 风险

| 风险 | 缓解 |
|---|---|
| Context token 增长 | 只投影 selected capability 的 datasets，并复用现有 max_chars/section 裁剪 |
| 模型把 coverage 当授权 | 明确 evidence 是 advisory；ToolRegistry/Domain preflight 继续强校验 |
| 旧 snapshot 字段缺失 | 空对象/unknown 兼容，不改变旧计划和 artifact 迁移 |
| 把 GIS 字段写入公共业务逻辑 | 只使用 generic dataset evidence keys，GIS 仅提供数据来源 |
