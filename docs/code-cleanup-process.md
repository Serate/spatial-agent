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

新对话或新一轮清理开始时，按以下顺序阅读：

1. `docs/agent-context-resume.md`
2. `docs/task-resume.md`
3. `docs/agent-development-issues.md`
4. `docs/code-cleanup-plan.md`

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
- `docs/task-resume.md`
- `docs/agent-context-resume.md`

## 八、可复制检查清单

- [ ] 阅读恢复文档、任务文档、问题记录和清理计划。
- [ ] 检查 Git 状态、当前提交、用户已有修改和数据/密钥边界。
- [ ] 统计候选并区分死代码、兼容代码、有效入口和独立测试。
- [ ] 用 `rg` 搜索导入、动态入口、文档、脚本、profile 和 fixture 引用。
- [ ] 复核重复 fixture 是否属于同一协议，复核测试是否有独立失败模式。
- [ ] 按 P0/P1/P2/P3 小批量修改，不做无证据的大规模删除。
- [ ] 运行受影响测试、静态检查、compileall、profile 和必要环境验收。
- [ ] 记录实际结果、跳过原因、保留/删除判定和新问题。
- [ ] 检查 staged diff，提交、推送并确认工作树与远端同步。
