# M330 阶段交接

## 状态

- 阶段：`M330` 通用 Agent 开放问题质量与纵向行为验收
- 状态：M330-A 进行中；正在固定通用直接回答场景矩阵并补齐最小契约验证
- 基线：M329 完成后的工作区版本待提交
- 协作：单 Agent，最大并发度 1；测试、真实模型和 GIS 优先使用 Docker

## 当前目标

验证 general Runtime 能处理非预定义的多领域问题，并把直接回答、能力发现、受控行动、澄清、降级、恢复和答案体验连成
用户可感知的 Agent 行为。当前不引入 RAG，不新增固定领域分支。

## 已完成

- M329 已将产品 `/runs`、preview、async、events、Artifact 和 CLI 默认切换到 `general` Runtime；显式 Domain 入口不变。
- M329 已验证真实模型直接回答、经济工具链、白名单 Web 降级、工具提案审批和同一 Run 恢复。
- M329 已完成 SQLite/Artifact 重启、多轮续问、SSE `Last-Event-ID`、Docker 精简回归和答案上下文状态修复。

## M330-0 验收

- 已建立 `capability-map.md`、`spec.md`、`plan.md` 和本 handoff。
- 下一步先固定代表性场景矩阵和预期公共投影，再修改代码；不读取完整历史或模型原文。

## 必要文件

- `agent/general_runtime.py`
- `agent/general_capability_host.py`
- `agent/runtime_core/react_runtime.py`
- `agent/llm_planner.py`
- `agent/answer_generation.py`
- `agent/result_summary.py`
- `agent/run_events.py`
- `agent/application/http.py`
- `agent/service.py`
- `production_api.py`
- `serve_api.py`
- `run_demo.py`
- `web/src/console_result_projection.js`
- M330 紧凑测试及必要的现有 ReAct/答案/HTTP 测试

## 恢复规则

只读取 `docs/agent-work-state.md`、`tasks/current-state.md`、本 handoff、M330 Plan 中当前子任务涉及的源码和测试。真实模型输出、
Prompt、密钥、完整历史和全量测试按需读取，不作为默认上下文。

## 阻塞与下一步

- 阻塞：无。
- 当前动作：建立非数据普通问题矩阵，验证 direct-answer 的公共 Result/Request Mode/answer-generation 投影；若发现语义缺陷只做领域中立修复。
