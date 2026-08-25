# Plan: M279 自然语言 Composite Planner

## 实施顺序

1. **Catalog projection**：定义并测试跨 Domain 能力的最小有界投影，复用现有 catalog/workflow/result/readiness，不读取无关领域源码。
2. **Planner contract**：定义规划请求/响应与 planner evidence；让 Rule/LLM adapter 输出同一候选 Composite request；为 fake LLM、非法 JSON、provider failure 保留 seam。
3. **Planning Application**：实现 resolve → plan → validate/repair → clarify/submit 显式阶段；成功调用 M278 `CompositeRunApplication`，失败不创建 execution run。
4. **HTTP/CLI boundary**：在 `HTTPApplication` 增加一个 semantic command，并让 FastAPI/stdlib 映射同一语义；不修改已有 Composite lifecycle 路由。
5. **Docker verification**：运行 M279 定向测试、M278/M277 regression、compileall、architecture strict、CI/stage；真实模型只做显式单 case。
6. **Documentation and delivery**：更新 `docs/agent-work-state.md`、中文问题日志、milestones 和恢复卡，提交推送；根据项目全局规划前端动态 Composite View 与真实跨入口验收。

## Likely files

- `agent/application/composite_planning.py`（新增）
- `agent/composite_planner.py` 或现有 planner adapter seam（按实际调用图选择）
- `agent/application/http.py`
- `production_api.py`
- `serve_api.py`
- `tests/test_m279_composite_planner.py`
- `tests/test_m279_composite_http.py`

## Verification checkpoints

| Checkpoint | Evidence |
|---|---|
| Projection | 跨 Domain context 只有 allowlisted capability/data/result 字段 |
| Plan | Rule/LLM/failure 都落入同一 bounded plan response |
| Gate | invalid plan 在 coordinator 前被拒绝，repair lineage 可读 |
| Execution | 合法计划返回稳定 M278 run_id，结果/evidence 可查询 |
| Cross-entry | FastAPI/stdlib semantic command 一致，旧 M278 路由回归通过 |
