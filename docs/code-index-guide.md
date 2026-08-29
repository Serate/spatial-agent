# 源码功能索引维护指南

`docs/code-index.json` 是机器生成的源码导航索引，不复制源码正文。它回答三个问题：文件在哪一层、承担什么职责、应该从哪里验证。索引由
`scripts/build_code_index.py` 根据 `docs/code-index-overrides.json` 生成；`scripts/build_agent_module_map.py` 再将其中全部
`agent/` 条目生成可人工阅读的 [`agent-module-responsibilities.md`](agent-module-responsibilities.md)。

职责盘点与物理归类是两个阶段：本阶段先保证每个文件的职责、语义层、稳定性和验证入口可见；只有结合导入图、公共
seam 和实际变化点后，下一阶段才决定是否移动目录。不能把语义层名称直接当作迁移指令。

## 语义来源

每个索引条目都有 `semantic_source`：

- `file-override`：关键文件的精确职责、阶段、依赖或测试映射，以文件路径为键维护。
- `path-rule`：按目录或文件前缀继承的职责，用于稳定的职责簇；越具体的前缀优先级越高。
- `default`：没有被分类。当前校验器禁止它进入已生成索引，避免语义覆盖率悄悄下降。

索引顶层的 `semantic_index` 提供 `classified_files`、`file_override_files`、`path_rule_files`、
`default_files` 和 `coverage_percent`。这里的 100% 表示每个文件都有可导航的语义标签，
不表示每个文件都经过人工逐行理解；职责簇仍应通过关键文件 override 和测试映射校准。

## 当前物理目录结构

项目采用“稳定公共入口 + 深模块职责簇”的结构：

```text
agent/
├── application/   用例与 HTTP 语义编排
├── runtime_core/  Runtime 规划、执行、恢复和投影
├── tooling/       工具提案、沙箱和审批治理
├── react/         ReAct 决策契约与循环
├── network/       受控网络搜索适配器
└── analysis/      领域中立分析引擎
domains/
├── gis/           GIS Domain Pack 与适配器
├── economic/      Economic Domain Pack
├── indicators/    指标 Domain Pack
└── text/          Text Domain Pack
web/src/            Console canonical source
scripts/            稳定命令入口、数据处理、验收和校验脚本
```

`agent/` 根目录保留公共契约、稳定导入入口和兼容 facade。不要为了目录数量而机械搬动这些
模块：如果移动会迫使大量调用方改 import，应先建立新的深模块接口、迁移调用方并保留有明确
生命周期的单向兼容 facade。`web/` 根目录的少量 JS 文件同理，它们是旧调用方的兼容入口，
canonical 前端实现位于 `web/src/`。

本轮已完成第一批物理归类：GIS 数据目录、manifest、探测、质量、栅格、空间和几何 Adapter
全部以 `domains/gis/adapters/` 为唯一实现路径；`agent/` 根目录不再保留这些重复转发文件。
测试、脚本和 Runtime 工厂直接依赖 Domain Adapter。剩余公共契约暂不搬动，避免为了减少文件
数量制造大量浅层兼容模块。

本阶段又完成两类归类：Application 的 Service 异步、格式化、会话和状态实现位于
`agent/application/`；GIS 的 analysis-ready binding、release evidence、runtime capability
和 deterministic demo adapter 位于 `domains/gis/adapters/`。根目录对应路径只保留单向兼容 facade，
并由架构守卫单独登记。`agent/application/__init__.py` 使用惰性导出，避免低层支撑模块导入整个
Application 用例包而形成循环。

## 维护流程

新增文件时：

1. 如果属于已有职责簇，扩展最具体的 `rules` 前缀；如果是公共稳定 seam，再添加精确
   `files` override。
2. 如果形成两个以上实际变化的实现，再考虑新增目录/模块 seam；只有一个实现时优先保持
   现有深模块，避免制造浅层转发。
3. 运行 `python scripts/build_code_index.py` 和
   `pwsh -NoProfile -File scripts/validate_code_index.ps1`。
4. 运行 `python scripts/build_agent_module_map.py` 更新 `agent/` 全量职责地图。
5. 只有职责确实变化时才更新 `role`、`layer` 或 `stage`；不要把提交编号当作职责。

Docker/CI 可以在阶段收口时重复生成索引，但不应把生成的绝对路径、私有数据、Prompt、模型
原文或密钥写入索引。
