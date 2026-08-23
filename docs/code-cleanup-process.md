# 代码清理流程

本文档是 Spatial Agent 后续代码清理的操作手册。清理目标不是单纯减少文件或测试数量，而是在不破坏 Agent Runtime 公共契约、兼容入口、真实环境验收和可观测证据的前提下，降低无效复杂度。

适用范围包括：运行代码、Domain Pack、Planner、ToolRegistry、HTTP/Console 入口、评测脚本、测试、fixture、profile、文档和可选 GIS/模型/Docker 入口。

## 一、清理前的约束

开始前必须遵守以下规则：

1. 先做项目全局盘点，再处理局部候选。要说明候选问题服务于哪个产品能力、架构边界或测试证据。
2. “没有直接调用”不等于“死代码”。动态导入、字符串路由、`__getattr__`、`__all__`、反射序列化、CLI、HTTP、PowerShell、Docker 和可选 profile 都可能是有效入口。
3. 不按测试数量删除测试。只有在确认没有独立失败模式、恢复路径、跨入口价值或环境契约后，才可以合并。
4. 不把兼容 facade、legacy schema、历史 artifact 读取和可选真实环境入口当成无效代码。
5. 不提交 API key、token、私有配置或原始 GIS 数据；不使用宽范围递归删除。
6. 最大并发度遵循当前恢复文档的有效规则；共享契约的修改按依赖顺序单线程完成。

## 二、恢复上下文并建立基线

新对话或新一轮清理开始时，只读取短快照：

1. `docs/agent-context-current.md`
2. `docs/code-cleanup-plan.md`（仅当本轮确实是代码清理）

`docs/agent-context-resume.md`、`docs/task-resume.md` 和
`docs/agent-development-issues.md` 现在都是短入口或近期问题索引；历史档案必须先用
`scripts/resume_context.ps1 -Topic ...` 有界检索，禁止全文读取。

然后检查工作树和当前阶段：

```powershell
git status --short --branch
git log -1 --oneline --decorate
git diff --stat
git diff --check
```

记录以下基线：

- 当前阶段目标和全局缺口，而不是只记录一个待删除文件。
- 运行代码、脚本、评测和测试文件数量；测试方法数量只作为观察值，不能作为删除指标。
- 当前 `quick`、`ci`、`stage`、`full-stage`、GIS、live、Docker 入口及其环境前提。
- 工作树中已有的用户修改。清理时不能覆盖或重置无关修改。

## 三、收集候选并分类

候选收集至少覆盖四类：

### 1. 静态候选

使用静态工具和文本搜索发现：

- 未使用 import、局部变量、参数和不可达分支。
- 低置信度 dead code 报告。
- 已删除文件的残留引用。
- 旧测试模块名、过期 profile 描述和失效命令。

推荐先用仓库内可复现的入口：

```powershell
rg --files agent domains evaluation scripts tests
rg -n "TODO|FIXME|旧名称|旧 profile|deleted-file-name" agent domains evaluation scripts tests docs
```

静态工具若没有加入 PATH，优先使用当前 Python 环境的模块入口：

```powershell
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' -m ruff check agent domains evaluation scripts tests --select F401,F821,F841
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' -m pyflakes agent domains evaluation scripts tests
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' -m vulture agent domains evaluation scripts tests --min-confidence 100
```

工具未安装时应记录“环境缺口”，不能把未执行静态检查写成通过；也不能直接根据 Vulture 的低置信度结果删除代码。

### 2. 入口与契约候选

对每个候选搜索：

- Python 相对导入和公共旧导入。
- README、API 文档、workflow、PowerShell 和 Docker 配置。
- HTTP 路由、CLI 参数、profile 字符串和动态 registry。
- artifact/recovery 读取、JSON 序列化字段和前端消费字段。
- 正向、负向、失败、恢复、跨入口和真实环境测试。

### 3. 重复测试与 fixture 候选

先区分“数据重复”和“证据重复”：

- 同一测试协议、完全相同的模型响应，可以复用一个 canonical fixture。
- 带有 `domain`、provider metrics、turns、expected 的自包含回放 suite，即使包含相同响应，也可以为了可移植性保留内嵌副本。
- 同一请求从 CLI、HTTP、artifact、recovery 或 Console 验证不同边界时，不能仅因输入相同而删除测试。
- 只有重复运行、没有新断言的 profile 调用才适合合并；独立失败模式必须保留。

### 4. 注释和文档候选

搜索过期数字、旧 profile 组合、已删除文件名和历史命令。区分：

- 当前有效说明：必须修正。
- 历史里程碑记录：保留原始事实，不批量改写。
- 问题复盘：保留现象、根因和预防措施，必要时追加中文记录。

## 四、逐项作出保留或删除判定

每个候选都要填写或口头确认以下判断：

| 判断项 | 是 | 否 |
| --- | --- | --- |
| 仓库内存在直接调用或导入 | 保留或继续定位真实归属 | 进入入口复核 |
| 存在 CLI/HTTP/脚本/profile/动态入口 | 保留 | 继续检查契约和文档 |
| 属于兼容 facade、旧 schema 或序列化字段 | 默认保留 | 继续检查 |
| 有独立失败、恢复、跨入口或环境证据 | 保留 | 继续检查是否只是重复执行 |
| 有 canonical fixture 可替代且协议相同 | 复用 fixture | 保留自包含数据 |
| 删除后有专项回归覆盖 | 可以进入小批量修改 | 先补证据，不删除 |

只有同时满足“无入口、无契约、无文档引用、无兼容责任，并且已有回归替代”时，才允许删除运行代码或测试。

## 五、按风险分批修改

按以下顺序实施，每批都保持可回滚和可验证：

### P0：确定无效项

先清理未使用 import、局部变量、测试替身参数和明确无效的样板。不要在这一批改变公开 API、结果字段或入口行为。

### P1：实现归属和重复实现

如果是 Domain 实现迁移：

- 先把实现放入 Domain-owned 模块。
- 公共层只保留协议和惰性兼容 facade。
- 避免 facade 顶层导入造成循环依赖。
- 同时验证实现模块路径、旧导入、惰性加载和跨入口结果。

### P2：死代码和动态入口审计

对没有直接 import 的模块逐个完成入口搜索。保留脚本、动态 provider、registry 查询方法、反射字段和可选环境入口，删除前必须有明确证据。

### P3：测试、fixture 和文档收口

- 复用完全相同且属于同一协议的 canonical fixture。
- 把 profile 重复执行收敛到职责清晰的入口。
- 不删除独立失败、恢复、跨入口、真实数据和领域隔离测试。
- 当前说明、恢复文档、里程碑、清理计划和问题记录同步更新。

## 六、验证顺序

先执行最小范围，再逐步扩大：

1. `git diff --check`。
2. 受影响模块的 unittest；执行前用 `rg --files tests` 确认真实模块名，不能凭历史简称拼命令。
3. Ruff、Pyflakes、Vulture 和 compileall。
4. `quick` 或对应专项 profile。
5. 阶段收口时执行 `ci`、`stage`；共享 Runtime、HTTP、SQLite 或部署改动才追加更重矩阵。
6. GIS、真实模型和 Docker 只在对应代码、数据卷或部署边界变化时显式运行，不能把旧环境结果当作当前提交证据。

常用命令：

```powershell
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' -m compileall -q agent domains evaluation scripts tests
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' scripts\test_profile.py --profile quick
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' scripts\test_profile.py --profile ci
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' scripts\test_profile.py --profile stage
```

失败时先分类：

- 命令入口错误：模块不存在、参数过期、编码或路径问题。
- 代码回归：断言、schema、plan、Runtime 或结果契约失败。
- 环境问题：FastAPI、Rasterio、GDAL、Docker、真实数据或 provider 不可用。

三类问题不能混写成“测试失败”，应分别记录和处理。

## 七、收尾和提交

阶段完成前检查：

- 变更只包含本轮清理和必要文档。
- 没有 API key、token、私有配置、原始 GIS 数据或临时输出。
- `git diff --check` 和代表性测试通过。
- 文档记录实际测试数量、跳过原因、环境限制和保留/删除理由。
- 历史里程碑数字没有被当前结果覆盖。

提交前执行：

```powershell
git diff --check
git status --short
git diff --stat
git add <明确列出的文件>
git diff --cached --check
git diff --cached --stat
git commit -m "refactor: <简短清理目标>"
git push origin main
git status --short --branch
git rev-list --left-right --count main...origin/main
```

推送后必须确认工作树干净，且本地与远端计数为 `0 0`。阶段文档至少同步：

- `docs/code-cleanup-plan.md`
- `docs/agent-development-issues.md`（若发现新的工程问题）
- `docs/milestones.md`
- `docs/agent-context-current.md`
- `docs/archive/context-history/`（仅保存阶段历史，不作为启动输入）

## 八、本轮清理复盘：可直接复用的执行流

下面是本轮 M132 代码清理实际采用的流程。后续清理应优先按这个顺序执行，只有在发现新的风险类型时才扩展流程，不要一开始就对整个仓库做大规模删除。

### 第 1 步：建立数量和边界基线

先记录运行代码、脚本、评测、测试文件和测试方法数量，同时记录当前 Git 状态、阶段目标、测试 profile 和环境限制。本轮基线为 105 个运行/脚本/评测 Python 文件、124 个测试文件、695 个测试方法。

这些数字只用于观察清理前后变化，不是删除目标。清理前还要明确以下内容：

- 哪些目录属于运行时公共边界，哪些属于 Domain-owned 实现。
- 哪些脚本由 CLI、PowerShell、workflow、Docker 或文档直接调用。
- 哪些测试覆盖失败、恢复、跨入口、领域隔离或可选环境。
- 哪些文件包含兼容导出、旧 artifact/schema 读取或序列化字段。

### 第 2 步：先收集报告，再人工确认

本轮先通过 AST/import 扫描建立初始候选；静态工具可用后，再使用 Ruff、Pyflakes 和 Vulture 复核。两类结果都只是候选列表，不是删除清单。

对每个候选至少回答四个问题：

1. 它是否被直接导入或调用？
2. 它是否通过字符串、反射、`__getattr__`、CLI、HTTP、profile 或序列化被间接使用？
3. 它是否承担兼容、恢复、部署或环境验收责任？
4. 删除后是否仍有专项测试覆盖原来的失败模式？

本轮静态报告中有意保留了 capability discovery 的兼容导出、Domain Pack 惰性 provider、结果 registry 查询方法、CLI 脚本和反射序列化字段；它们“直接调用较少”不代表无效。

### 第 3 步：形成候选判定表

不要直接在编辑器里凭感觉删除。每个候选先记录一行判定结果：

| 候选 | 发现来源 | 入口复核 | 契约/兼容责任 | 独立测试 | 处理 |
| --- | --- | --- | --- | --- | --- |
| 未使用 import/局部变量 | Ruff/Pyflakes/AST | 无 | 无 | 受影响模块回归 | 删除 |
| 低置信度 Vulture 报告 | Vulture | 动态入口存在 | 有 | 有 | 保留并注明原因 |
| 旧 facade/alias | 搜索/静态报告 | 旧导入或文档引用 | 有 | 兼容回归 | 保留或惰性委托 |
| 重复 fixture | 规范化 JSON 比较 | 协议相同或不同 | 视 suite 而定 | fixture 回归 | 复用或保留自包含副本 |
| 重复 profile 调用 | profile 脚本 | 同一入口重复执行 | 无新增信号 | profile 回归 | 合并职责 |

只有“无入口、无契约、无文档引用、无兼容责任，并且已有回归替代”的候选，才进入删除批次。

### 第 4 步：按低风险到高风险分批

本轮的有效顺序是：

1. 清理无效 import、未使用局部变量和测试替身参数。
2. 迁移领域实现时，把真实实现移动到 Domain-owned 模块，公共层只保留协议和惰性兼容 facade。
3. 审计没有直接 import 的模块，确认 CLI、HTTP、动态 registry、artifact/recovery 和可选环境入口。
4. 审计重复 fixture、重复 profile 和重复断言，只合并没有独立证据价值的部分。
5. 最后同步清理计划、里程碑、恢复文档和中文问题记录。

每批修改应尽量只解决一种问题。不要把“删除无效导入”“迁移领域实现”“修改公共 result schema”混在同一个不可定位的大批次中。

### 第 5 步：区分“数据重复”和“证据重复”

本轮删除了与 M67 canonical 模型响应逐字重复的独立 M65 fixture，并让 M65 测试读取 canonical response；但 M127 领域回放中的相同响应仍保留，因为它属于带 domain、turns、metrics 和 expected 的自包含协议。

后续判断 fixture 时使用以下规则：

- 同一协议、同一响应、同一读取方式：优先复用 canonical fixture。
- 不同协议、跨领域或要求独立复制运行：保留自包含 fixture，并记录理由。
- 同一请求但断言边界不同：保留测试，不因输入相同而删除。
- 只有 profile 重复调用且没有新增断言：合并入口，不删除底层契约测试。

### 第 6 步：用“受影响回归”证明每一批清理

清理阶段不应每改一行就运行全量测试，也不能只运行全量测试。推荐顺序为：

1. `git diff --check`。
2. 受影响模块/契约的专项测试。
3. Ruff、Pyflakes、Vulture、compileall。
4. `quick`、`ci` 或 `stage` 中与改动风险匹配的 profile。
5. 阶段收口时只统一运行一次代表性专项和一次全量离线回归。

本轮验证重点是：静态问题清理后的受影响专项、Domain 归属/兼容回归、异步/恢复/重规划/profile 专项、fixture 读取回归，以及 `ci`、`stage`、编译和 diff check。真实 GIS、live 模型、FastAPI 和 Docker 依赖按环境单独判断，不能用“跳过”写成“通过”。

### 第 7 步：遇到异常先判断类型

清理过程中出现失败时，先把问题归类，再决定是否继续清理：

- 命令问题：模块名过期、profile 参数错误、路径或编码错误。
- 代码回归：schema、导入、计划、Runtime、结果或恢复断言失败。
- 环境问题：依赖缺失、真实数据不可用、Docker/provider 不可用。
- 清理误判：删除了动态入口、兼容字段或独立测试证据。

命令问题不能当成代码回归；环境问题不能通过删除测试掩盖；清理误判应立即恢复该候选并补入口/契约测试。

### 第 8 步：满足停止条件后再收口

出现以下任一情况时，应暂停删除并重新规划，而不是继续扩大清理范围：

- 候选涉及公共 schema、result envelope、Runtime 状态或持久化格式，但兼容策略未确定。
- 找不到完整入口证据，无法判断是否存在动态调用或外部用户依赖。
- 删除会同时改变多个 Domain、HTTP、artifact 或恢复边界。
- 测试失败原因尚未区分是代码、命令还是环境。
- 需要修改真实数据、私有配置、API key 或仓库外部署目录。
- 本轮清理已经从降低复杂度变成新增功能或架构重构。

收口时必须能回答：删了什么、为什么能删、保留了什么、为什么不能删、哪些环境尚未验证，以及下一轮还剩哪些高风险候选。

## 九、最近一次领域归属清理复盘

M139 暴露的不是普通死代码，而是“公共模块里残留领域策略”的结构性问题：GIS 的 intent 和 clarification 规则虽然可以从公共模块调用，但它们并不属于通用 Runtime。后续遇到类似问题时，按下面的流程处理。

### 1. 先判断代码的真实归属

- 看代码表达的是通用运行时行为，还是某个 Domain 的词汇、能力和业务规则。
- 不因为代码位于 `agent/` 或被多个入口调用，就认定它属于公共层。
- 将“被调用位置”和“应该拥有规则的位置”分开记录；公共调用不等于公共所有权。

### 2. 先迁移实现，再决定是否删除旧入口

- 在 `domains/<domain>/` 中建立真实实现，并让 Domain Pack 暴露明确的协议 seam。
- 公共模块只保留必要的惰性兼容 facade；facade 不得重新承载领域判断，也不得在顶层导入领域实现造成循环依赖。
- 旧导入、旧函数签名和必要的序列化行为先保持兼容，等迁移证据充分后再安排弃用或删除。

### 3. 验证“新归属”和“旧兼容”两条路径

至少覆盖以下断言：

- 领域实现可以从 Domain-owned 模块直接调用。
- 旧公共导入仍能按约定工作，并且是惰性委托而非重复实现。
- Text 等其他 Domain 不会继承 GIS 词汇、候选能力或澄清字段。
- Planner、preview、run、HTTP 和结果 envelope 使用同一 clarification contract。
- 兼容路径不会改变错误分类、结果类型或可读执行轨迹。

### 4. 识别迁移后暴露的下一层硬编码

领域归属迁移完成后，再检查是否仍存在类似下面的分支：

```python
if capability_id in ("some_capability", "another_capability"):
    missing.append("某个字段")
```

这类代码通常说明能力需求没有进入 CapabilityCatalog。不要把新能力继续追加到 `if capability_id` 列表中，应将实体、数据集、约束和澄清字段声明为能力元数据，再由通用澄清逻辑投影为 `missing` 和 `next_actions`。这属于下一阶段架构改进，不应在一次清理中顺手扩大为无边界重构。

### 5. 本轮迁移的收口证据

M139 的有效证据组合为：领域实现归属专项、旧 facade 兼容专项、Text/GIS 隔离专项、历史 intent 回归，以及完整离线 profile。后续类似清理至少应保留一条直接归属测试、一条兼容测试和一条跨领域隔离测试；若影响 HTTP 或持久化，再追加对应入口回归。

## 十、清理记录模板

每轮清理在 `docs/code-cleanup-plan.md` 中增加一条简短记录，至少包含以下字段：

| 字段 | 要记录的内容 |
| --- | --- |
| 候选 | 文件、符号、fixture 或 profile 名称 |
| 发现来源 | Ruff、Pyflakes、Vulture、AST、`rg`、测试失败或架构复盘 |
| 真实入口 | import、HTTP、CLI、动态 registry、序列化、恢复或可选环境入口 |
| 风险判断 | 公共契约、兼容、领域归属、测试证据、部署或数据风险 |
| 处理决定 | 删除、迁移、保留、复用 fixture、合并 profile 或延期 |
| 处理理由 | 为什么不会丢失能力或证据；若保留，说明其责任 |
| 验证证据 | 专项测试、静态检查、profile、GIS/live/Docker 结果及跳过原因 |
| 后续动作 | 弃用窗口、补测试、下一阶段架构任务或环境修复 |

推荐使用下面的最小记录格式：

```text
候选：<文件/符号>
来源：<工具或复盘入口>
归属与入口：<公共/Domain/兼容/动态入口>
决定：<删除/迁移/保留/复用/延期>
理由：<保留或删除的证据>
验证：<专项测试与 profile；跳过项及原因>
后续：<没有则写“无”>
```

## 十一、可复制检查清单

- [ ] 阅读恢复文档、任务文档、问题记录和清理计划。
- [ ] 检查 Git 状态、当前提交、用户已有修改和数据/密钥边界。
- [ ] 统计候选并区分死代码、兼容代码、有效入口和独立测试。
- [ ] 用 `rg` 搜索导入、动态入口、文档、脚本、profile 和 fixture 引用。
- [ ] 复核重复 fixture 是否属于同一协议，复核测试是否有独立失败模式。
- [ ] 按 P0/P1/P2/P3 小批量修改，不做无证据的大规模删除。
- [ ] 运行受影响测试、静态检查、compileall、profile 和必要环境验收。
- [ ] 记录实际结果、跳过原因、保留/删除判定和新问题。
- [ ] 检查 staged diff，提交、推送并确认工作树与远端同步。
