# 整体架构拆分规划（Deep-Module 导向）

> 目标：把当前 `agent/` 里的 God 模块按"深模块"原则拆开——**小接口 + 大实现，放在干净的 seam 上**。
> 用词遵循 `codebase-design`：模块（module）、接口（interface）、实现（implementation）、深度（depth）、seam。
> **规则：任何拆分必须让原模块保持为 compat facade，补回它此前暴露的每一个公共符号（含被 `import *` 漏掉的 `_underscore` 符号），并以此前教训（runtime/service 拆分造成的 re-export 缺口）为红线。** 每拆一处，用"全量测试模块导入扫描"验证没有 import regression。

## 现状（God 模块与行数）

| 模块 | 行数 | 主要职责混杂点 |
|---|---|---|
| `persistence/sqlite_store.py` | 1939 | 多个 Store 类 + 连接/重试/迁移混在一起 |
| `application/composite_planning.py` | 1866 | 组合规划编排 + response 归一化 |
| `llm_planner.py` | 1708 | `LLMPlanner` 编排 + `OpenAIPlannerClient` provider 传输 + ReAct 决策整形 |
| `runtime_core/runtime_engine.py` | 1345 | `AgentRuntime`（刚从 runtime.py 拆出者） |
| `runtime_core/run_lifecycle.py` | 1229 | 生命周期状态机 + 事件投影 |
| `answer_generation.py` | 1198 | 流式/预算编排 + 上下文构建 + 答案证据安全投影/消毒 |
| `application/service_facade.py` | 1178 | `AgentService` 实现 + 资源生命周期 + 场景编排 |
| `workflow_templates.py` | 1161 | 模板目录 + 编译器 |
| `runtime_core/planner_envelope.py` | 1047 | 有界规划信封 |

## 拆分原则（每项）

1. **Seam 必须真实**：只在有"确实会变"的地方拆出 seam；单一 adapter 意味着假设性 seam，不拆。
2. **深度优先**：新模块小接口（少数函数）+ 大实现；从没把接口膨胀到和实现一样复杂。
3. **compat 红线**：原模块保留为 compat facade，补回全部公共符号；新增 `import *` 类 facade 必须显式补 `_underscore` 符号（`import *` 不会导出它们）。
4. **验证**：每拆一处，host 侧跑「全量测试模块导入扫描」+ 受影响测试；最后用 Docker full-regression 测计数。

## 候选拆分（按可行性与价值）

### A. `answer_generation.py` → `agent/answer_evidence.py`（已落实并验证）
- **Seam**：答案"安全证据投影 + 消毒"与"LLM 流式/预算编排"之间。
- **新深模块** `agent/answer_evidence.py`：`project_answer_generation_evidence` / `fallback_answer_generation_evidence` + 一组纯消毒助手（`_project_value` / `_safe_*` / `_normalize_stream_text` / `_contains_internal_reference` / `_is_stream_fallback_eligible` / `_stream_fallback_reason` / `_normalize_composite_answer`）+ 常量（`_OMITTED_KEYS` / `_MAX_*`）+ `ANSWER_GENERATION_SCHEMA_VERSION`。
- **理由**：这些是纯函数、只依赖 `project_answer_quality` + 常量，是最干净的"安全证据"边界；外部仅消费 `fallback_answer_generation_evidence` / `project_answer_generation_evidence`。
- **compat**：`answer_generation.py` 从新模块 re-import 公共与 `_underscore` 助手并 re-export 公共符号，内部引用与外部导入均不变。
- **验证**：`compileall` 通过；host 全量测试模块导入扫描无新增失败；`tests.test_answer_generation` 5/5 通过。

### B. `llm_planner.py` → `agent/integration/openai_client.py`（已落实并验证）
- **Seam**：`OpenAIPlannerClient`（provider 传输 + URL/HTTP/设置 + 响应解码）与 `LLMPlanner`（规划编排 + ReAct 决策整形）之间。
- **⚠ 循环导入红线**：`OpenAIPlannerClient` 内部直接使用上述模块级助手。**不能**只搬类、把助手留在 `llm_planner.py` 再由 `openai_client.py` `from .llm_planner import`，否则 `llm_planner.py`⇄`openai_client.py` 循环导入。**必须整簇一起搬**（类 + 它依赖的助手），`llm_planner.py` 只 re-import + re-export。
- **落实**：`agent/integration/openai_client.py` 已承载 `OpenAIPlannerClient` + `_provider_progress` + 全部 URL/HTTP/设置/响应解码助手（25 个符号）；`agent/llm_planner.py` 保留 `LLMPlanner`/`LLMClient`/ReAct 决策助手，并 re-export 这 25 个符号（兼容外部导入与 `LLMPlanner` 在 156/161 行对 `_normalize_shortcut_plan`/`_has_output_type` 的引用）。
- **验证**：`compileall`、host 全量测试模块导入扫描（仅 fastapi 环境项）、client 实例化、`test_m304/m305/m2_llm_planner/m320_react` 共 58 项 tests 通过。

### C. `sqlite_store.py`（1939）→ 按 store-scope 拆分（待评估）
- **Seam**：`SQLiteStateStore` / `SQLiteConversationStore` / `SQLiteDecisionStore` / `SQLiteToolApprovalStore` 各自为独立 adapter；连接/重试/迁移抽到 `agent/persistence/sqlite_retry.py` + 连接工厂。
- **风险**：中心持久化，是"真实资产"；低优先级，用 `storage` 专项测试保护。

### D. `workflow_templates.py`（1161）→ 目录/编译器拆分（待评估）
- **Seam**：模板目录（catalog）与模板编译器（compile/validate）分离。

### E. `run_lifecycle.py`（1229）→ 生命周期事件投影拆分（待评估）
- **Seam**：状态机推进 vs 安全事件投影。

## 已拆分项与未做项

- 本轮落实：A（answer_evidence）、B（openai_client）、C（composite_planning_projection）、D（workflow_templates 四模块）、E（runtime_helpers）、F（sqlite_store → `sqlite_common` + `sqlite_conversation_store` + 保留 state store）——均已实现并验证。F 用三模块结构（共享连接/row helper 进 `sqlite_common`）避免 sqlite_store⇄conversation 循环，`sqlite_store` 保留 `SQLiteStateStore` 并 re-export `SQLiteConversationStore`；复验核心 sqlite/async 测试通过（仅 Windows 临时文件锁为环境项）。
- 待做：G（`run_lifecycle`/`service_facade` 大类别拆分）需逐项做 seam 评估 + compat 验证后再动。

## 完成标准

> 验证口径（本次约定）：**不跑 full-regression 全量矩阵（太慢）**。改用「受影响测试 + 精简 profile」。

1. 每个新增/重命名 module 都过 `compileall`、host「全量测试模块导入扫描」（除 fastapi 环境依赖外为 0）。
2. 受影响测试模块 `unittest` 跑通；涉及共享 Runtime/SQLite/HTTP 契约时补 `python scripts\test_profile.py --profile quick` 及必要 `smoke`。
3. 不跑 full-regression；如需更广覆盖，仅按失败边界追加受影响模块专项，不重跑 1663 用例。
4. `scripts/architecture_check.py` 保持 `status: ok`，不新增 God-module 预警。
5. 更新 `docs/architecture-map.md`、`docs/agent-module-responsibilities.md`、code-index 与热状态。
