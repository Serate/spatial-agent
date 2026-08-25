# 当前任务状态账本

> 上下文恢复时只读取本账本的当前阶段和最近记录。历史阶段结论在对应 Spec/Plan、milestones 和中文问题日志中；不要把本文件重新扩展成完整历史。

## 当前阶段

- 阶段：M281 动态 Composite 结果体验与跨入口一致性（已完成）
- 阶段规划：
  - `docs/m281-dynamic-composite-capability-map.md`
  - `docs/m281-dynamic-composite-spec.md`
  - `docs/m281-dynamic-composite-plan.md`
- 执行方式：串行；默认测试离线精简；真实模型、GIS、Docker 和浏览器只做显式验收

## 最近任务记录

### M281-A：全局能力图、Spec、Plan（已完成）

- 目标：让用户从自然语言请求得到简洁答案，并由同一 Composite Result/View/Evidence 驱动 CLI、HTTP、前端和 artifact。
- 改动：创建 M281 能力图、Spec、Plan；明确公共 Projection、答案边界、generic renderer 和跨入口验收；不增加 GIS/Economic 专用页面分支。
- 验证：规划覆盖产品、架构、模型、数据、部署、体验、测试七个维度。

### M281-B：公共 Composite View Projection（已完成）

- 目标：从 canonical Composite Result 生成版本化、受限、领域中立的 `spatial-agent.composite-view.v1`。
- 改动：新增 `agent/composite_view.py`；`CompositeRunApplication.get_view()` 与 `HTTPApplication.read("composite_view")` 复用同一投影；补成功、partial、敏感字段过滤契约。
- 验证：M281/M278/M279 Docker 定向回归 **16/16**。

### M281-C：简洁答案与结构化结果一致性（已完成）

- 目标：让 Composite answer 来自 canonical facts，支持 headline、summary、key findings、limitations 和安全 fallback。
- 改动：扩展 `agent.answer_generation`；Projection 接受经过校验的 answer override，模型失败不能改变 state、fingerprint 或 canonical facts。
- 验证：M281 + answer-generation + M278 + M279 Docker 回归 **21/21**。

### M281-D：CLI/HTTP/前端/artifact 一致性（已完成）

- 目标：FastAPI、stdlib、前端和 artifact 对同一 run 使用相同 Projection、答案、View IDs、evidence references 和 fingerprint。
- 改动：新增 `/composite-runs/{run_id}/view` 两入口路由；前端 `projectionToPanels()` 将 Projection 的 `views[]` 适配为 generic renderer，答案区和对话消息优先使用 Projection answer；未增加领域分支。
- 验证：M281/M278/M279 Docker **19/19**；compileall、architecture strict、JS syntax、renderer smoke、地图 browser smoke 和 Composite Projection browser smoke 通过。默认 overview smoke 的旧问句进入结构化澄清，未将其误报为成功。
- 明确文件：`agent/composite_view.py`、`agent/application/composite_runs.py`、`agent/application/http.py`、`production_api.py`、`serve_api.py`、`web/src/console_app.js`、`web/src/console_renderer_registry.js`、`tests/test_m281_dynamic_composite.py`。

### M281-E：阶段收口与全局重规划（已完成）

- 目标：更新 M281 Spec/Plan、milestones、中文问题日志、快照和阶段清单，提交并推送版本；随后基于项目全局七维度规划下一阶段。
- 改动：已同步 M281 实施状态、浏览器澄清边界、恢复快照和精简任务账本；`docs/agent-project-direction.md` 与当前串行 goal 对齐。
- 验证：`git diff --check`、敏感信息扫描通过；阶段代码和 Docker/browser 验收已记录；待提交并推送本阶段版本。
- 阻塞：无。浏览器 overview 默认问句需要澄清，属于测试输入与当前规划契约不匹配，不影响 Composite Projection 验收。
- 下一步：提交推送 M281；随后从全局七维度规划 M282。

## 更新协议

1. 开始、完成或暂停子任务时，更新对应记录的状态、目标、文件、验证、阻塞和下一步。
2. 阶段收口时，把完整结论归档到阶段 Spec/Plan 或 milestones；本文件只保留当前阶段和最近记录。
3. 恢复上下文只读取本文件、当前阶段规划，以及当前任务明确列出的文件。
