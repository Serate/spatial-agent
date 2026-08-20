# 代码清理计划

本文档记录 Spatial Agent 的代码清理范围、判定依据和阶段结果。清理目标是减少无效复杂度，同时保持 Agent Runtime 的公共契约、兼容入口和可选环境验收能力不变。

## 当前统计

统计范围：`agent/`、`domains/`、`scripts/`、`evaluation/` 下的 Python 代码，以及 `tests/` 中的回归契约。

- 运行/脚本/评测 Python 文件：105 个。
- 测试 Python 文件：124 个。
- 初始清理基线时 Ruff、Pyflakes、Vulture 尚未安装，因此先用 AST 导入扫描；当前已安装到本机 Python 环境，并用静态工具和模块契约逐项复核。
- 初始 AST 复核确认无调用证据的导入或局部导入：23 个，分布在 12 个模块。
- 安装静态工具后又发现并清理 25 个真实问题：6 个运行代码问题、19 个测试代码问题；另有 4 个 capability discovery 导出是有意兼容导出，已用 `__all__` 明确标记而不是删除。
- 测试中另有 15 个只用于协议签名或测试替身、但未读取的参数名，已改成下划线命名；没有测试方法被判定为无入口死代码。
- 测试规模基线：124 个测试文件、695 个测试方法；测试方法名和方法体都没有发现跨文件重复。测试代码本轮删除无效导入、规范未使用参数、收敛 profile 重复执行，并将 profile 测试的重复 subprocess 样板抽成 helper；不删除有独立契约的测试方法。
- 暂不删除的代码：兼容 facade、legacy route、旧 artifact/schema 读取、可选 live/GIS/Docker 入口，以及具有独立契约价值的历史测试。

已确认的 23 个无效导入为：

| 模块 | 无效导入 | 判定 |
| --- | --- | --- |
| `agent/memory.py` | `json`、`Iterable`、`Mapping` | 文件内无引用 |
| `agent/service.py` | `ConcurrencyLimited`、`SQLiteConversationStore`、`SQLiteStateStore`、`_as_float`、`_epoch_to_iso`、`_round_ms`、`_crs_name`、局部 `math` | 全文无调用；局部 `math` 也未参与计算 |
| `agent/rule_planning.py` | `Iterable`、`Mapping` | 兼容 facade 未使用 |
| `agent/dataset_manifest.py` | `DatasetEntry` | 只导入未使用 |
| `domains/gis/rule_planning.py` | `parse_spatial_request` | 组合器不负责请求抽取 |
| `domains/text/composer.py` | `Iterable`、`StepRun` | 摘要组合器不使用 |
| `domains/text/domain.py` | `REQUEST_FACTS_SCHEMA_VERSION` | 只使用 `RequestFacts` |
| `domains/text/runtime.py` | `DomainPack` | 仅使用解析 helper |
| `evaluation/global_runner.py` | `List` | 使用内置泛型/其他类型 |
| `evaluation/live_baseline.py` | `classify_provider_error` | 当前 live 基线没有调用 |
| `scripts/prepare_analysis_rasters.py` | `Mapping` | 参数和实现未使用 |
| `scripts/release_evidence.py` | `os` | 脚本未使用环境模块 |

## 清理顺序

### P0：确定无效、低风险

删除上表 23 个导入，并清理静态工具发现的 25 个同类问题；运行受影响模块测试、`compileall` 和 `git diff --check`。这一步不改变公开 API，也不删除文件。

### P1：重复实现和归属收口

完成 GIS Planner/Composer 的物理归属迁移：公共 `agent/` 只保留协议和有界兼容 facade，领域策略保留在 `domains/gis`。兼容入口必须通过测试证明仍可用，不能因为“看起来重复”直接删除。

### P2：可疑死代码审计

对没有直接 import 的模块逐个检查：命令行入口、动态导入、HTTP 路由、配置声明、artifact/recovery 读取和 optional profile 都算有效入口。只有同时满足“无入口、无契约、无文档引用、可由专项回归证明替代”才允许删除。

本轮审计结果：

- 修正相对导入解析后，`agent/`、`domains/`、`evaluation/` 没有孤立运行模块；Domain Pack 的惰性导入、结果 registry 和 evidence provider 均有调用链。
- `scripts/` 中没有直接 import 的文件都是明确的 CLI/验收入口，并被 README、API 文档、PowerShell、profile 或专项测试引用；不删除这些脚本。
- 删除了 `AgentService._ensure_memory_session()`、`ServiceState` 中 7 个无调用的旧 runtime/session/memory-job 操作，以及两个测试替身中只赋值不读取的字段。
- 保留 `__getattr__`、`KNOWN_TOOLS`、`validate_template`、结果 registry 查询方法和反射序列化字段；它们虽可能被静态工具标为低置信度未使用，但分别承担兼容导出、旧调用、公共查询或 JSON 序列化职责。

### P3：测试与文档收口

测试不按数量简单删除。只把重复 profile 调用、没有独立断言的重复场景和过期 fixture 归并；保留跨入口、失败、恢复、真实数据和领域隔离契约。清理结果同步到 `docs/milestones.md`、`docs/task-resume.md`、`docs/agent-context-resume.md` 和本项目问题记录。

## 判定规则

1. 无引用的 import 可以直接清理；动态导出、`__all__`、`__getattr__`、字符串路由和兼容读取必须人工复核。
2. 兼容代码不是无效代码，除非有明确的弃用窗口和迁移证据。
3. 删除模块前必须搜索 CLI、HTTP、Docker、workflow、配置和文档入口。
4. 每批清理都要有行为回归证据；不能用“全量测试暂时通过”替代具体契约验证。
5. 清理过程中发现新的架构问题，用中文追加到 `docs/agent-development-issues.md`。

## 当前进度

- P0 统计与计划：已完成。
- P0 导入和测试无效代码清理：已完成静态修改和专项回归确认。
- P1 GIS Planner 物理归属：已实现并通过归属、兼容和跨领域专项验收。
- P2 可疑死代码审计：已完成入口图、低置信度候选、动态入口、重复断言和过期运行注释复核；未发现新的可安全删除项。
- P3 测试与文档收口：已删除与 `m67_spatial_overview_model.json` 响应逐字重复的 `m65_spatial_overview_response.json`，M65 Runtime/ToolRegistry 测试改为复用 canonical response；M127 领域回放中的内嵌响应仍保留，以保证回放 suite 自包含。跨入口、失败、恢复、真实环境和领域隔离断言均保留，M132.2 已收口。
