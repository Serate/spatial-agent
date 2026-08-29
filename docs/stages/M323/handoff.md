# M323 阶段交接

## 当前状态

- 阶段：M323 人工审批、持久化和 Registry 治理
- 当前任务：M323-D，阶段收口与全局重规划
- 状态：已完成，待提交并进入 M324 全局规划
- 前置版本：M322 `1b0bcdc`
- 恢复入口：`docs/agent-work-state.md`、`tasks/current-state.md`、本文件

## 已完成

- M322 已提供脱敏 `tool-proposal-receipt.v1`，合法提案只能停留在 `awaiting_approval`。
- 文件功能索引生成器已扩展为 Python/JavaScript，Docker 已生成 299 个源码文件（260 Python、39 JavaScript）。
- 文档索引已分为热状态、阶段包、稳定知识和历史归档四层。
- 文档架构校验已通过，默认恢复只读取热快照、索引、当前状态和本交接文件。

## 已完成

- M323-A 审批契约、状态机、receipt fingerprint、幂等与版本保护已完成。
- M323-B SQLite approval store 已接入 ServiceState，支持状态过滤、过期转换和重启恢复；恢复时保留有界 Registry definition，不保留源码。
- M323-C 已将 approved definition 通过 ToolRegistry 发布，Runtime dispatch 对未批准、撤销和版本/指纹漂移 fail closed。
- M323-D 已通过共享 HTTPApplication 暴露列表、详情、批准、拒绝和撤销语义，stdlib 与 FastAPI 使用同一应用 seam。
- 发现并修复两个问题：Docker 测试复用生产 `SPATIAL_AGENT_STATE_DB` 导致旧 rejected 状态污染；SQLite 反序列化丢失 definition。均已加入回归测试。

## 必要文件

- `docs/stages/M323/capability-map.md`
- `docs/stages/M323/spec.md`
- `docs/stages/M323/plan.md`
- `docs/code-index.json`
- `docs/code-index-overrides.json`
- `agent/tooling/proposal.py`
- `agent/tooling/__init__.py`
- `agent/tools.py`
- `agent/persistence/sqlite_store.py`
- `agent/tooling/approval.py`
- `agent/application/http.py`
- `agent/application/service_state.py`
- `agent/service.py`
- `agent/runtime_core/react_runtime.py`
- `tests/test_m323_tool_approval.py`

## 验证与阻塞

- `validate_document_index.ps1` 和 `resume_context.ps1` 默认/M323 主题恢复验证通过。
- `build_code_index.py` 已支持 Python/JavaScript；索引计数、符号行号、文档索引和主题查询均已校验通过。
- `validate_code_index.ps1` 已修复为仅校验覆盖项实际声明的测试路径，前端无测试覆盖时不会误报空路径。
- M323-A～D 定向 Docker 契约 11/11；M322 回归 7/7；阶段收口后需重建镜像并运行最终门禁。
- 阻塞：无。

## 下一步

完成最终 Docker 门禁后，从全局目标重规划 M324：前端/SSE/恢复/跨入口一致性。除非出现新的可证伪失败，不再扩展 M323 审批模型。
