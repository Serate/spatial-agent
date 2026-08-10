# Spatial Agent

Spatial Agent 是一个可替换、可观测、可测试的空间智能体 Runtime demo。它把自然语言空间问题转换为结构化任务计划，经工具契约校验后执行真实 GIS 或内存演示后端，并在前端展示答案、计划、步骤、轨迹、数据质量和空间结果。

## 核心功能

- 对话式空间分析：支持行政区边界、DEM 高程、坡度、土地利用、道路/水体和建设候选演示筛选。
- Agent Runtime：Planner、TaskPlan、依赖执行、重试、超时、取消和失败恢复相互分离。
- 双 Planner：默认规则规划器保证确定性；可选 OpenAI 兼容大模型规划器处理更开放的表达。
- 工具安全边界：所有工具经过 schema 校验和 Registry 分发，不让模型直接调用后端。
- 真实数据接入：支持行政区 GeoJSON、DEM/土地利用栅格，以及武汉 OSM 道路和水体 GeoPackage。
- 数据质量预检：检查可读性、CRS、覆盖关系和几何质量，并在分析结果中保留证据。
- 配置化工作流：Console 可选择版本化模板、编辑结构化约束和证据；运行前后按同一模板校验，并在异步/重启恢复中保留选择。
- 像元安全门控：DEM/土地利用联合分析要求明确网格对齐证据；仅有文件覆盖或 CRS 不一致时会在工具执行前解释性阻止。
- 证据驱动执行：健康报告声明数据可支持的操作；明确不可用时在下游工具前停止并解释原因。
- 可观测结果：中文答案、TaskPlan、执行轨迹、步骤结果、provenance、GeoJSON summary 和 JSON artifact。
- 异步运行观测：提供生命周期、排队/执行耗时、失败分类、取消和重启恢复状态，并聚合到 `/metrics`。
- Web Console：中文对话界面、会话切换、异步运行、结果面板、栅格覆盖范围和 GeoJSON 空间预览。
- 生产基线：Docker、Docker Compose、SQLite 持久化、健康检查和只读 GIS 数据挂载。

建设候选结果是演示筛选，不代表法定建设适宜性、规划许可、生态红线或其他行政结论。

## 架构

```text
用户请求
  -> RuleBasedPlanner / LLMPlanner
  -> TaskPlan 与 schema 校验
  -> AgentRuntime
  -> ToolRegistry
  -> SpatialToolAdapter
  -> InMemorySpatialBackend / HybridSpatialBackend
  -> 中文答案、trace、artifact、地图结果
```

## 环境要求

- Python 3.10 或更高版本。
- 仅运行内存演示或离线测试时不需要 GIS 第三方依赖。
- 真实 GIS 需要 Conda 环境 `spatial-agent-gis`，包含 GeoPandas、Rasterio、GDAL 和 PROJ。
- 生产部署需要 Docker Desktop、WSL2 和 Docker Compose。

## 快速启动

### 内存演示

```powershell
python run_demo.py "查询洪山区行政区边界"
python run_demo.py "你好"
```

启动中文 Console：

```powershell
scripts\start_console.ps1 -Mode memory -Port 8088
```

浏览器访问 `http://127.0.0.1:8088/`。

### 真实 GIS

先创建环境：

```powershell
conda env create -f environment.yml
conda activate spatial-agent-gis
```

使用真实数据启动：

```powershell
scripts\start_console.ps1 -Mode gis -Port 8088
python run_demo.py --backend local "分析洪山区DEM高程概况"
python run_demo.py --backend local "分析洪山区土地利用分布"
```

武汉数据配置示例位于 `config/datasets.wuhan.local.example.json`。原始数据默认位于宿主机 `D:\dataset\agent` 和 `D:\tmp\wuhan-gis`，不提交到仓库。

### 真实模型

复制安全模板并编辑本地私有配置：

```powershell
Copy-Item config\openai.example.json config\openai.local.json
python run_demo.py --planner openai "查询DEM栅格元数据"
```

也可以通过环境变量设置 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_WIRE_API` 和 `OPENAI_REASONING_EFFORT`。`config/openai.local.json`、`.env.production` 和 API key 已被 Git 忽略，禁止提交。

默认规则规划器和 CI 不访问真实模型；真实模型 smoke 只有显式设置 `SPATIAL_AGENT_LIVE_OPENAI=1` 才运行。

## 生产部署

准备 `.env.production`，设置本地数据目录和服务配置后执行：

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml up --build -d
```

检查服务：

```powershell
Invoke-RestMethod http://127.0.0.1:8088/health/ready
scripts\production_acceptance.ps1 -BaseUrl http://127.0.0.1:8088
```

生产容器固定 GIS 依赖，通过只读 volume 挂载宿主机数据；SQLite 保存会话和运行快照。生产环境不依赖操作员手动 `conda activate`。可通过 `SPATIAL_AGENT_ASYNC_WORKERS` 配置异步 worker 数量（1-16，默认 4），实际值可在 `/metrics.async_jobs.worker_count` 查看。

## HTTP API

详细请求和响应契约见 [`docs/api.md`](docs/api.md)。常用接口：

- `GET /health`
- `POST /runs`
- `POST /runs/async`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/observability`
- `GET /runs/{run_id}/async`
- `GET /capabilities/runtime`
- `GET /workflows`
- `POST /workflows/{template_id}/validate`
- `POST /workflows/{template_id}/revise`
- `GET /metrics`
- `POST /runs/{run_id}/cancel`
- `POST /runs/{run_id}/retry`
- `GET /sessions`
- `POST /sessions/{session_id}/clear`

## 测试与验证

```powershell
python -m unittest discover -s tests -v
python scripts\smoke_check.py
python scripts\evaluate_global.py --strict
```

GIS 回归需使用 GIS Python，并设置 `GDAL_DATA`、`PROJ_LIB`；启动控制台的 `scripts/start_console.ps1 -Mode gis` 会自动设置它们。阶段历史和每阶段验证记录见 [`docs/milestones.md`](docs/milestones.md)。

## 项目文档

- [`docs/milestones.md`](docs/milestones.md)：阶段完成记录、版本节奏和验证基线。
- [`docs/demo-checklist.md`](docs/demo-checklist.md)：离线、GIS、模型和失败路径演示清单。
- [`docs/spatial-agent-design.md`](docs/spatial-agent-design.md)：系统设计与模块边界。
- [`docs/core-acceptance.md`](docs/core-acceptance.md)：核心空间流程验收标准。
- [`evaluation/cases/global-acceptance.json`](evaluation/cases/global-acceptance.json)：全局场景验收矩阵。
- [`docs/agent-context-resume.md`](docs/agent-context-resume.md)：新对话恢复上下文。
- [`docs/task-resume.md`](docs/task-resume.md)：当前任务和下一阶段规划。
- [`docs/agent-development-issues.md`](docs/agent-development-issues.md)：中文工程问题记录。
- [`docs/data-adapter-plan.md`](docs/data-adapter-plan.md)：真实空间数据接入计划。

数据 manifest 可用 `scripts\dataset_manifest.py` 显式生成和校验；健康接口只做轻量 manifest 检查，完整 SHA-256 校验不会隐式发生。
武汉本地配置可以进一步绑定 manifest（输出文件应放在仓库外或保持被 Git 忽略）：

```powershell
python scripts\dataset_manifest.py `
  --config config\datasets.wuhan.local.example.json `
  --output D:\tmp\wuhan-gis\wuhan.manifest.json
python scripts\bind_dataset_manifest.py `
  --config config\datasets.wuhan.local.example.json `
  --manifest D:\tmp\wuhan-gis\wuhan.manifest.json `
  --output D:\tmp\wuhan-gis\datasets.wuhan.local.json
python scripts\dataset_manifest.py `
  --config D:\tmp\wuhan-gis\datasets.wuhan.local.json `
  --verify D:\tmp\wuhan-gis\wuhan.manifest.json `
  --evidence-output D:\tmp\wuhan-gis\wuhan.manifest.verification.json
scripts\start_console.ps1 -Mode gis `
  -DatasetConfig D:\tmp\wuhan-gis\datasets.wuhan.local.json `
  -RequireDatasetManifest
```

`/capabilities/runtime` 会显示 manifest 是否已绑定、轻量检查状态和校验模式；`-RequireDatasetManifest` 会让生产 readiness 在必需 manifest 缺失或不匹配时返回未就绪。

当原始 DEM 与土地利用栅格存在 CRS 或像元网格差异时，先生成分析就绪派生层，再绑定其 manifest：

```powershell
python scripts\prepare_analysis_rasters.py `
  --config config\datasets.wuhan.local.example.json `
  --output-dir D:\tmp\wuhan-gis\analysis-ready `
  --config-output D:\tmp\wuhan-gis\datasets.wuhan.analysis-ready.json
python scripts\dataset_manifest.py `
  --config D:\tmp\wuhan-gis\datasets.wuhan.analysis-ready.json `
  --output D:\tmp\wuhan-gis\analysis-ready\analysis.manifest.json
python scripts\bind_dataset_manifest.py `
  --config D:\tmp\wuhan-gis\datasets.wuhan.analysis-ready.json `
  --manifest D:\tmp\wuhan-gis\analysis-ready\analysis.manifest.json `
  --output D:\tmp\wuhan-gis\datasets.wuhan.analysis-ready.bound.json
```

该流水线使用武汉 13 区边界确定目标范围，默认生成 `EPSG:32649`、30 米共同网格；原始数据只读保留，派生层仍是 demo 分析证据，不代表法定规划结论。

## 数据与合规边界

武汉道路和水体演示数据来自 OpenStreetMap，遵循 ODbL provenance 要求；真实栅格和行政区数据由本地配置引用。所有空间结果均为 demo 分析，不能替代法定数据、规划审批或专业测绘结论。
