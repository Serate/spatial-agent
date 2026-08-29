# M325 阶段交接

## 当前状态

- 阶段：M325 真实模型 + Docker/GIS + 白名单搜索纵向验收
- 当前任务：阶段已完成，等待 M326 全局重规划
- 状态：已完成
- 恢复入口：`docs/agent-work-state.md`、本文件、`spec.md`、`plan.md`

## 已完成

- M323 已完成人工审批、SQLite 持久化、Registry gate 和 HTTP 治理语义。
- M324 已完成 approved 工具重启再绑定、版本/指纹失配 fail closed、安全审批投影和 Console
  工具治理面板；Docker M324 6/6、M323/M322 18/18、Node smoke、compileall、architecture
  strict、索引和 readiness 均通过。
- 已建立 M325 capability map、Spec 和 Plan；首个请求选择真实 GIS + ReAct + 可选白名单搜索，
  不自动下载未知数据。
- M325-A 真实 provider 探针成功；ReAct 缺少工具名的有限恢复失败已稳定分类为 planning/
  `invalid_model_response`，Docker M320 回归已扩展为 21/21 通过。
- 复杂真实请求已生成合法 `get_dataset_health_report` 动作；默认容器 `/data` 只有经济示例数据，
  健康工具因此返回 `backend_initialization_unavailable`。真实验收必须显式挂载 `D:\dataset\agent`
  到 `/data` 并使用容器数据配置。
- M325-A 后续补充了 ReAct 动作校验失败的有界部分恢复：先记录 blocked evidence，再基于已完成
  工具事实生成完成态；策略、权限、审批和执行策略错误仍保持 fail closed。
- 一次真实 `openai + local` GIS 请求在 Docker 中完成，结果为 `COMPLETED`，真实模型一次请求、
  0 次重试，artifact、轮询和 evidence endpoint 对比均为 `ok`；若模型后续动作校验失败，结果
  会明确表现为部分结论，不伪造未执行步骤。
- 白名单搜索离线契约 8/8 通过，覆盖白名单来源、空白名单、越界来源、重定向、超大响应、HTML
  投影、ToolRegistry 注册和 ReAct search executor；未访问外网。
- 同一真实 run 的 SSE 回放从事件 1 到 180 单调递增，`Last-Event-ID: 100` 从 101 续传到终态；
  重启临时 GIS 容器后，run/artifact/polling/evidence 恢复对比均为 `ok`。

## 必要文件

- `docs/stages/M325/capability-map.md`
- `docs/stages/M325/spec.md`
- `docs/stages/M325/plan.md`
- `scripts/live_provider_probe.py`
- `scripts/live_http_acceptance.py`
- `evaluation/live_provider_probe.py`
- `agent/integration/openai_config.py`
- `agent/llm_planner.py`
- `agent/runtime_core/react_runtime.py`
- `agent/react/loop.py`
- `agent/network/web_search.py`
- `domains/gis/domain.py`
- `config/datasets.container.example.json`

## 验证

- Docker `tests.test_m320_react_runtime` **21/21**、M325 Domain 契约 **1/1**、白名单搜索
  `tests.test_m321_web_search` **8/8** 通过。
- Docker compileall、`architecture_check.py --strict` 和默认/真实数据容器 readiness **200** 通过；
  architecture 仍仅保留既有 `runtime_god_module` 与 `service_god_module` 警告。
- 真实 HTTP 验收的 async/artifact、polling/artifact、evidence endpoints 和重启恢复均通过；未保存
  Prompt、模型原文、密钥或私有数据。

## 阻塞与下一步

- 阻塞：无。默认镜像继续使用仓库内示例数据；真实数据只通过一次性只读卷挂载。
- 下一步：完成 M325 版本提交后，按全局目标规划 M326，重点评估真实模型多步计划的完整性、
  部分恢复后的用户答案质量和跨入口可观测性，不为单一区域增加硬编码流程。
