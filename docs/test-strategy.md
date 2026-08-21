# Spatial Agent 测试分层策略

本项目默认测试策略从“每次跑完整矩阵”调整为“少量代表性 profile + 按需扩展矩阵”。目标是让开发反馈更快，同时保留真实 GIS、真实大模型和 Docker 生产验收的证据。提交/PR 使用专门的 `ci` profile，阶段收口再使用独立的 `stage`，避免每次提交重复执行所有边界场景。

测试执行环境统一以当前 Docker 镜像为准。日常 profile、Python 单元测试、GIS 依赖检查和阶段回归默认在容器内运行；宿主 Python 只用于诊断环境问题，不作为阶段通过证据。容器应先用 `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --force-recreate` 按当前工作树重建，并确认 `ai-agent-spatial-agent-1` 为 `healthy`。

跨入口结果一致性由 `evaluation/contract_harness.py` 提供统一投影。CLI、HTTP、artifact 和 recovery 验收必须通过 `normalize_result`/`compare_results` 比较稳定契约，不能在各测试文件中重新拼接 `result`、兼容顶层字段或自行忽略运行时字段。

结果视图同样由 Domain-owned `ViewSpec` 和 bounded view model 驱动。前端静态契约与跨领域专项可以验证 renderer 边界；动态 Chrome smoke 属于显式环境验收，不计入 compact/CI。

声明了 ViewSpec 但没有可展示数据时，公共 result contract 返回 `kind: unavailable` 及降级/artifact 状态；专项回归应比较同步结果与恢复 artifact 的 view projection，不能只断言 HTTP 状态码。

当前原则：默认入口只跑极少量代表性用例，不再按里程碑整模块执行。历史测试继续保留为专项诊断资产，但不能把 500+ 用例当成本地开发默认门禁。

## 默认门禁

### quick

日常改动默认运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile quick
~~~

覆盖范围：

- 2 个核心契约 tripwire：跨 Service/CLI/HTTP/artifact 的稳定结果投影，以及多轮澄清的会话边界。

`quick` 的目标是快速发现共享契约是否断裂，不负责证明每个历史里程碑都仍完整覆盖。

### smoke

服务 smoke 与 quick 分离，按需运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile smoke
~~~

覆盖范围：道路坡度、DEM 元数据、澄清追问和后续回答。`scripts/smoke_check.py` 默认只跑服务 smoke，不再嵌套完整 unittest。

### ci

提交/PR 默认门禁：

~~~powershell
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile ci
~~~

覆盖范围：

- `quick` 的 2 个核心契约 tripwire。
- 一次服务 smoke，验证 Service 入口、DEM 元数据和澄清续问。

`ci` 不运行阶段 acceptance、完整模型回放或历史里程碑测试；复杂场景和未注册能力仍保留在 `stage`，由阶段验收运行。

### stage

阶段代码收口但还未进入真实环境验收时运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile stage
~~~

覆盖范围是独立的 3 个代表性离线验收场景：通用问答、复杂空间分析模板、未注册空间问题澄清。它不重复运行 `quick`，也不运行服务 smoke、完整全局矩阵或脱敏模型回放。

~~~powershell
docker exec ai-agent-spatial-agent-1 python scripts/evaluate_global.py --cases evaluation/cases/stage-acceptance.json --strict --no-model-evaluation --no-model-replay
~~~

### full-stage

只有在改动共享 Runtime、HTTP/SQLite 契约、模型评测或阶段发布前需要更强证据时运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile full-stage
~~~

覆盖范围：`evaluation/cases/global-acceptance.json + 脱敏模型评测 + 多轮模型回放`。这是显式重型入口，不作为日常或普通阶段默认门禁，也不嵌套 `quick` 或 `smoke`。

## 真实环境验收

### gis-core

真实 GIS 核心契约只在 `spatial-agent-gis` 环境中运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile gis-core
~~~

该 profile 不替代完整 GIS 全量，但能快速覆盖行政区 GeoJSON、Rasterio 元数据和 analysis-ready 门控。它同样采用抽样用例，不再整模块跑真实 GIS 测试。

### live-short

真实模型默认不跑完整 live baseline。阶段验收只跑两个代表 case：

~~~powershell
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile live-short --dataset-config /app/config/datasets.container.example.json --live-output /app/outputs/live-short.json
~~~

代表 case：

- `live-gis-spatial-overview`：覆盖空间总览、多工具 DAG、同名工具多次调用和中文答案组合。
- `live-gis-constrained-buildability`：覆盖真实 DEM/土地利用 analysis-ready、道路/水体约束、建设候选门控和工具 schema。

使用 `--dataset-config` 显式绑定 analysis-ready 配置，避免默认 raw 栅格配置触发 `grid_mismatch` 并把数据准备问题误判为模型或 Planner 问题。

### docker

Docker profile 只做 production acceptance，不在容器里默认跑完整 live baseline：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\production_acceptance.ps1 -BaseUrl http://127.0.0.1:8088
~~~

`production_acceptance.ps1` 是宿主侧 HTTP 验收编排器，不能从 Linux 容器内运行；它验收的目标仍必须是当前重建的 Docker 容器。容器镜像构建、完整数据卷和容器内 live baseline 只在部署或数据卷改动阶段单独执行。

## 完整矩阵

以下命令仍保留，但不是日常默认：

~~~powershell
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile full-stage
docker exec ai-agent-spatial-agent-1 python -m unittest discover -s tests -t . -v  # 只运行 compact active suite
docker exec ai-agent-spatial-agent-1 python scripts/smoke_check.py --with-unit-tests
docker exec ai-agent-spatial-agent-1 python scripts/live_baseline.py --allow-network --backend local
~~~

历史里程碑测试仍可按模块显式运行，例如 `python -m unittest tests.test_m80_replanning -v`；它们不再参与默认 discovery。只有改动共享 Runtime、SQLite、HTTP 契约、生产部署、真实模型评测或数据卷配置时，才运行对应完整矩阵。提交/PR 不自动运行 `stage` 的边界场景；阶段收口或风险明确时再运行 `stage`。即使需要扩展矩阵，也应先跑失败范围最小的 profile，再按失败边界追加专项命令。

## 记录规则

- 阶段文档必须写明实际运行的是哪个 profile，而不是笼统写“测试通过”。
- live 结果只提交安全摘要，不提交 API key、本地私有配置、原始模型响应或原始 GIS 数据。
- 真实环境失败先分类为 provider、planner、tool schema、数据门控、GIS 后端或 Docker 环境，再决定是否修代码。

## M146 异步证据专项

涉及 result views、SQLite、artifact 或 HTTP 轮询时，优先运行一个跨重启的专项，断言 `spatial-agent.async-result-evidence.v1` 的状态、workspace/view 元数据和安全 artifact basename；不要把完整历史异步矩阵重新加入默认 discovery。当前专项为 `tests.test_m146_async_view_evidence`，默认 compact/CI 仍保持 4 项/quick 2 项。

## M147 artifact 兼容专项

涉及 artifact schema、Domain recovery 或 Console async evidence 时，显式运行 `tests.test_m147_artifact_compatibility`，覆盖当前版本、无版本历史文件、未知版本、跨 Domain、路径边界和通用前端消费。该专项不加入默认 discovery；M147 的 Docker 验收仅运行显式专项与 production acceptance。

## M163 workflow selection 生命周期专项

涉及 workflow selection、异步轮询、artifact-only recovery 或用户确认继续执行时，显式运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m163_workflow_selection_lifecycle -v
~~~

该专项验证同一选择证据在异步等待确认、SQLite/artifact 重启恢复和批准继续执行后的稳定投影；它不加入默认 quick/CI。阶段收口时再与 M148/M151-M162 相邻契约、Docker production acceptance、必要的浏览器和 `live-short` 一起执行。
