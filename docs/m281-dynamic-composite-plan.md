# Plan: M281 动态 Composite 结果体验与跨入口一致性

1. **A 公共投影契约**：盘点现有 Result/View/Evidence/Artifact 边界，新增领域中立的 Composite View Projection builder 和 schema 校验；先用 fake 结果锁定预算与状态语义。
2. **B 答案组合**：复用现有 answer generation/composer seam，从 canonical facts 生成简洁答案结构；补充 key findings、limitations、partial/failure fallback，不保存模型原文。
3. **C 通用前端 renderer**：让前端按 `data_profile` 和 View contract 动态创建结果区、地图/表格/指标/趋势/来源；收紧默认信息层级，详细 trace/evidence 折叠。
4. **D 入口一致性**：接入 CLI、HTTP、artifact 和前端；对同一 fingerprint 比较 projection、answer、View IDs、evidence references，异步读取不复制投影逻辑。
5. **E 分层验收**：Docker 重建后运行精简 contract/HTTP、真实 GIS + Economic projection 和 browser smoke；live 模型只做显式 probe，失败保持安全降级。
6. **F 阶段收口**：更新中文问题日志、milestones、工作账本和 README/部署说明（如有必要），提交推送后从产品、架构、数据、模型、部署、体验、测试七维度全局重规划。

## 实施记录（2026-08-25）

- A：已创建能力图、Spec、Plan，锁定领域中立 Projection 和答案边界。
- B：已实现 `agent/composite_view.py`、统一 HTTP read seam 和有界状态/证据/artifact 投影。
- C：已实现结构化 Composite answer、LLM adapter 与 deterministic fallback；答案生成不能改写 canonical facts。
- D：已接入 FastAPI/stdlib `/composite-runs/{run_id}/view`；前端 renderer registry 提供 `projectionToPanels()`，`console_app.js` 优先消费 Projection answer/views。
- D 验收：Docker M281/M278/M279 **19/19**；compileall、architecture strict、JS syntax、renderer smoke、地图 browser smoke、Composite Projection browser smoke 通过。
- E：当前进行文档收口、问题记录、版本推送和全局重规划；不在本阶段扩大默认测试或引入领域专用分支。

## 读取范围

- `docs/m281-dynamic-composite-capability-map.md`
- `docs/m281-dynamic-composite-spec.md`
- `docs/m281-dynamic-composite-plan.md`
- 当前任务账本明确列出的 Result/View/answer/frontend/HTTP 文件
