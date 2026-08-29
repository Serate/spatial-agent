# Spec：Agent 物理职责归类

## Objective

将 `agent/` 中已经确认的职责簇落实为 canonical 物理目录，降低根目录实现密度，提高开发者和 Agent 的可导航性；同时保留稳定公共导入路径，避免目录整理变成行为重写。

用户是维护 Agent Runtime 的工程师，需要能够根据职责快速定位实现、接口和验证入口。成功后的体验是：公共入口仍然可用，新的实现只在一个 canonical 位置维护，兼容入口明确且可追踪。

## Assumptions

1. 这是一次渐进式物理重构，不改变 HTTP、CLI、SQLite/artifact、Domain Pack、Result/View/Evidence 和 ReAct 的外部语义。
2. `agent.<old_module>` 是现有公共导入的一部分；迁移期间保留单向兼容 facade，确认无引用后再删除。
3. `agent/` 根目录中标记为 `public-boundary` 的契约和稳定门面不因“目录整齐”而强行搬动。
4. 当前工作区已有未提交修改，迁移只触碰本 Spec/Plan 明确的文件，不覆盖或回滚其他改动。
5. Python、GIS、Docker 和阶段验收优先在 Docker 中执行；文档、索引和纯导入检查可使用本地工具。

## Commands

```powershell
# 构建/更新部署镜像
docker compose -f docker-compose.prod.yml build

# 生成并校验导航索引
docker exec ai-agent-spatial-agent-1 python scripts/build_code_index.py
docker exec ai-agent-spatial-agent-1 python scripts/build_agent_module_map.py
pwsh -NoProfile -File scripts/validate_code_index.ps1
pwsh -NoProfile -File scripts/validate_document_index.ps1

# Docker 内最小 Python 验证
docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains scripts
docker exec ai-agent-spatial-agent-1 python scripts/architecture_check.py --strict
```

## Project Structure

```text
agent/
├── application/       Application 用例与共享支撑实现
├── runtime_core/      Runtime 规划、执行、恢复和投影
├── tooling/           工具注册、提案、沙箱和审批
├── react/             ReAct 决策契约与循环
├── network/           受控网络搜索
├── analysis/          领域中立分析引擎
├── persistence/       Artifact、SQLite、Memory canonical 实现（首批新增）
├── integration/       Provider 配置、运行能力和模型证据 canonical 实现（首批新增）
└── 根目录              公共契约、稳定入口和有明确生命周期的兼容 facade
domains/               Domain Pack 与 Domain-owned adapter
tests/                 通过 canonical seam 验证行为；兼容导入只保留少量 smoke
docs/stages/           阶段能力图、Spec、Plan、交接
```

## Code Style

canonical 实现使用明确的包内导入；根目录兼容入口只能做单向导出，不复制业务逻辑：

```python
"""Compatibility import for the canonical persistence seam."""

from .persistence.sqlite_store import SQLiteStateStore

__all__ = ["SQLiteStateStore"]
```

规则：目录名使用小写名词；canonical 模块保持原文件名以降低迁移噪声；兼容入口标明
`Compatibility`，不新增策略、状态机或 Domain 分支；生产代码优先导入 canonical 路径。

## Testing Strategy

- 索引层：生成 `code-index` 和职责地图，校验 100% 语义覆盖和无悬空条目。
- 迁移层：Docker `compileall`、架构 strict、canonical import smoke，以及兼容入口 import smoke。
- 行为层：每个职责簇只运行一组受影响的紧凑契约；不因纯移动重复运行全量业务测试。
- 阶段收口：Docker readiness、已有最小 service smoke 和一个跨入口结果契约；真实模型不因物理移动重复调用。
- 失败检查：旧路径不得出现第二份实现；canonical 与 facade 的公共符号保持一致；架构守卫不得把真实模块误标为 compat。

## Boundaries

- Always：先更新 Spec/Plan 和交接；使用 `git mv` 保留历史；canonical 只有一个实现；运行索引与导入门禁；不保存密钥、Prompt、模型原文或私有数据。
- Ask first：改变公共导入语义、删除兼容入口、修改数据库 schema、修改 CI/Compose 策略、引入新第三方依赖。
- Never：`git reset --hard`、覆盖用户未提交修改、把公共真实模块塞进 compat 豁免、跨 Domain 复制 Runtime 策略、为目录数量制造空壳模块。

## Success Criteria

1. 首批三类职责簇分别有清晰 canonical 目录，生产引用指向 canonical 路径。
2. 旧公共导入在迁移期间仍可用，兼容入口是单向、无逻辑复制的薄模块。
3. `agent/` 职责地图、code-index、architecture strict 和 document index 一致反映新路径。
4. Docker 内 compileall、导入 smoke、受影响紧凑契约和 readiness 通过。
5. 不改变任何既有 Run、Result、Evidence、Artifact、SQLite/restart、HTTP 或前端行为。
6. 每个迁移批次都有交接记录、修改文件、验证结果和下一批风险。

## Open Questions

- 首批迁移完成后，根据实际导入图决定 `result-evidence` 和 `planning` 是否继续物理下沉；不预先承诺把所有公共契约移出根目录。
