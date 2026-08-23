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

### live-http

HTTP/异步/artifact 的真实模型一致性使用独立 opt-in 脚本，默认不进入 CI：

~~~powershell
docker exec -e SPATIAL_AGENT_LIVE_HTTP=1 ai-agent-spatial-agent-1 python scripts/live_http_acceptance.py --planner openai --backend memory
~~~

先用 `--planner rule` 做无模型费用预检。live 路径只输出有界的 result type、模型身份与 usage、context/plan fingerprint、workspace/view panel 和比较状态；不写文件，不输出 prompt、provider 原始响应、API key 或宿主路径。同一 run 的 full result、polling、artifact 必须严格保持 plan/model evidence 一致；两个独立 live run 允许 plan fingerprint 不同，但核心结果投影必须一致。

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

## M164 selection interaction 专项

涉及候选能力、缺失事实、显式 workflow、用户确认或恢复动作时，显式运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m164_selection_interaction tests.test_m163_workflow_selection_lifecycle tests.test_m162_workflow_selection -v
~~~

该专项验证同一 `spatial-agent.selection-interaction.v1` 在 result、异步、artifact、HTTP 和 Console 静态 seam 中的状态与动作边界；容器没有 Node 时允许专项中的 Node 测试跳过，但阶段收口必须补跑宿主 Node smoke。HTTP 还应验证：当前 GIS Domain 的 confirmation → confirm → `COMPLETED`、非法动作 400，以及 interaction read 不泄露原始请求和工具参数。该专项不加入默认 quick/CI。

## M165 跨入口与真实浏览器专项

涉及 selection interaction、跨入口结果比较、静态 Console 资源、SQLite 多 worker 或旧 schema 时，阶段收口运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m165_cross_entry_contract tests.test_m164_selection_interaction tests.test_m163_workflow_selection_lifecycle tests.test_m68_sqlite_migration tests.test_m69_sqlite_matrix -v
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile quick
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile stage
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\production_acceptance.ps1 -BaseUrl http://127.0.0.1:8088
node scripts\console_selection_interaction_smoke.js
node scripts\console_selection_interaction_browser_smoke.js
~~~

浏览器命令需要先用 `scripts\console_cdp_start.ps1 -Headless` 启动独立 CDP profile；如果容器内没有 Node，专项中的 Node 测试允许跳过，但必须在宿主补跑静态 Node smoke。浏览器 smoke 只断言页面状态、结构化 interaction 和允许动作，不读取或输出原始请求、工具参数、密钥或模型响应。

## M166 request identity 与跨入口恢复专项

涉及请求语义、plan fingerprint、async polling、artifact-only recovery、SQLite 重启或 Contract Harness 时，显式运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m166_request_identity -v
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m165_cross_entry_contract tests.test_m164_selection_interaction tests.test_m163_workflow_selection_lifecycle tests.test_m158_evidence_registry tests.test_m156_execution_timeline tests.test_m155_plan_quality_contract tests.test_m153_action_lifecycle tests.test_m148_contract_harness -v
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile quick
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile stage
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\production_acceptance.ps1 -BaseUrl http://127.0.0.1:8088
~~~

M166 专项应覆盖 transport 配置不影响 request identity、计划 fingerprint 漂移可报告、同步/async/artifact/restart 共用 identity，以及带 spatial context 的真实 Service 链路。production acceptance 的 async/artifact Harness 失败必须先定位语义字段是否在 SQLite 快照和 artifact 中持久化，不能通过从比较器排除 identity 来掩盖漂移。

M166 选择与开放请求补充专项：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m166_multi_candidate_selection tests.test_m148_contract_harness -v
~~~

该专项验证 Domain 声明歧义时 Planner 前停止、`select_capability` 经 Domain seam 续接、Text/GIS 同步与异步共享核心 Contract。`async_result_evidence` 是异步入口的可选投影：所有入口都有时严格比较；同步入口没有时只比较公共核心证据，不能把 transport 专属字段当作业务结果漂移。

## M169 交互 receipt 与预览指纹专项

涉及交互动作 CAS、旧 artifact 迁移、Planner 选择证据、repair lineage 或预览计划绑定时，阶段收口还应运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -W error::ResourceWarning -m unittest tests.test_m169_interaction_receipt tests.test_m127_runtime_action_contract -v
node scripts\console_selection_interaction_browser_smoke.js
~~~

该浏览器 smoke 使用当前 Docker HTTP 服务和宿主隔离 Chrome CDP，验证预览 fingerprint、提交计划和最终完成结果保持一致，并确认 artifact 与选定能力存在。仓库未声明 `package.json` 时，浏览器脚本必须使用显式 CommonJS 异步入口，不能依赖 Node 对顶层 `await` 的模块推断。Python 测试仍统一在 Docker 内执行；宿主 Node 只负责前端静态/浏览器验收。

## M170 生命周期与跨 Domain 专项

涉及 FastAPI 生命周期、全局 Service 所有权或非 GIS Domain artifact 时，运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -W error::ResourceWarning -m unittest tests.test_m170_runtime_boundaries tests.test_m169_interaction_receipt -v
docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains production_api.py serve_api.py
~~~

M170 使用 `app.router.lifespan_context(app)` 验证 ASGI 生命周期，不依赖未安装的 `httpx2`/`TestClient`；生产 acceptance 仍通过宿主 PowerShell 调用当前 Docker HTTP 服务。FastAPI 生命周期测试不应因为测试客户端缺失而跳过，也不应为测试便利把额外 HTTP 客户端依赖加入生产镜像。

## M173 模型选择与修复证据专项

涉及 capability catalog、Planner selection、compact context、repair lineage 或跨入口证据时，运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m173_selection_contract tests.test_m160_evidence_completeness tests.test_m166_request_identity tests.test_m166_multi_candidate_selection tests.test_m169_interaction_receipt tests.test_m172_capability_discovery -v
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile quick
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile stage
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\production_acceptance.ps1 -BaseUrl http://127.0.0.1:8088
docker exec -e SPATIAL_AGENT_LIVE_OPENAI=1 -e SPATIAL_AGENT_LIVE_GIS=1 ai-agent-spatial-agent-1 python scripts/test_profile.py --profile live-short --dataset-config /app/config/datasets.container.example.json --live-output /app/outputs/live-short.json
node scripts\console_selection_interaction_browser_smoke.js
~~~

该专项要求 Contract Harness 比较 `planner_selection` 和脱敏 `repair_lineage`，忽略 latency/occurred_at 等易变字段；同时验证已知能力错配为 `mismatch`、未知结果为 `unresolved`、多候选为 `ambiguous`。live-short 只作为显式验收，不进入默认 CI，也不得提交原始模型输出、密钥或 GIS 数据。

## M174 Replay/Live selection evidence 专项

涉及 replay/live 报告、workflow selection 状态或 Planner alignment 汇总时，运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m174_replay_selection_evidence tests.test_m173_selection_contract tests.test_m150_repair_evaluation tests.test_m149_plan_repair_evidence -v
docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains evaluation result_contract.py
~~~

该专项只检查脱敏 projection 和公共状态，不重复真实模型请求；真实 live-short 仍按 M173/阶段风险显式执行。workflow `ambiguous`、planner `mismatch`、planner `unresolved` 必须保持不同状态，summary 不能通过合并状态来掩盖选择问题。

## M175 Evidence Registry selection 专项

涉及 Evidence Registry、异步/artifact 恢复或 selection completeness 时，运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m175_selection_registry tests.test_m158_evidence_registry tests.test_m160_evidence_completeness -v
docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains evaluation result_contract.py
~~~

当前严格完整性版本为 `spatial-agent.evidence-completeness.v2`，required entries 包含 workflow/planner selection；旧 Registry 允许兼容读取，但不能在当前严格 replay/Contract Harness 中伪装为完整。新增 Registry entry 时必须同步更新 schema 版本、完整性测试、async/artifact projection 和跨 Domain 契约。

## M221/M222 live HTTP、重启恢复与动态结果视图专项

涉及真实模型 HTTP/async/artifact 一致性或进程重启后的 existing-run 恢复时，显式运行：

~~~powershell
docker exec -e SPATIAL_AGENT_LIVE_HTTP=1 ai-agent-spatial-agent-1 python scripts/live_http_acceptance.py --verify-run-id <run-id> --planner <rule|openai> --backend <memory|local>
~~~

`--verify-run-id` 只读取已有 run、polling、artifact 和 evidence endpoint，不提交新请求、不调用模型。验收比较同一 run 的 result type、model/context/plan identity、workspace/view、Registry projection 和 recovery；输出保持有界，不保存原始模型响应。

旧非地图 renderer 清理后的最小 Console 验收为：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m30_console_result_summary tests.test_m66_console_acceptance tests.test_m148_console_domain_static -v
node scripts/console_health_smoke.js
node scripts/console_overview_smoke.js
node scripts/console_error_badge_smoke.js
node scripts/console_session_smoke.js
~~~

四个浏览器 smoke 必须串行复用 CDP 页面。它们验证统一动态结果容器、地图插件、错误空态和会话 identity；不得重新增加 raster/health/overview/composite/buildability 专用 DOM 断言。

## M223 Console 插件边界专项

Renderer/Action/GIS plugin 或 Console Shell 发生变化时，先重建当前 Docker 镜像，再运行一组小而正交的验收：

~~~powershell
docker compose -f docker-compose.prod.yml up -d --build
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m30_console_result_summary tests.test_m124_domain_actions tests.test_m148_console_domain_static tests.test_m165_cross_entry_contract -v
docker exec ai-agent-spatial-agent-1 node scripts/console_plugin_smoke.js
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile quick
docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains production_api.py serve_api.py
node scripts/console_overview_smoke.js
node scripts/console_clear_smoke.js
~~~

该专项只保留四类证据：Shell 领域隔离、Action Catalog/schema、renderer 故障/代次保护、真实浏览器的 generic/visual surface 与选择 reset。`console_overview_smoke.js` 同时验证动态 Action 表单，因此不再为每个 GIS Action 保留固定表单 smoke。地图交互使用内联 GeoJSON；真实 GIS 数据和 live planner 仍走显式 GIS/live profile，不能由 fixture 代替。

## M224 多 Domain Host 专项

Host、显式领域 HTTP 路由、SQLite 会话/幂等隔离或 Console 领域切换发生变化时，在当前 Docker 镜像中运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m224_domain_runtime_host tests.test_m224_domain_persistence tests.test_m224_domain_http -v
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m134_domain_registry tests.test_m170_runtime_boundaries tests.test_m171_domain_defaults -v
docker exec ai-agent-spatial-agent-1 node scripts/console_plugin_smoke.js
node scripts/console_domain_browser_smoke.js
node scripts/console_clear_smoke.js
~~~

该专项验证同一进程中的 GIS/Text Service 隔离、全部领域启动恢复、URL/body 领域一致性、会话固定领域、跨领域幂等、artifact 访问身份，以及切换下拉后仍按原领域轮询。浏览器脚本必须先有界确认隔离 CDP，串行复用一个页面；live 模型和真实 GIS 不进入该专项。

## M225 自动 Domain 路由专项

Selector、跨 Domain discovery、路由 lineage、自动入口或 Console 智能选择发生变化时，在当前 Docker 镜像中运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m225_domain_selector tests.test_m225_domain_routing_persistence tests.test_m225_domain_entrypoints -v
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m224_domain_runtime_host tests.test_m224_domain_persistence tests.test_m224_domain_http -v
docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains production_api.py serve_api.py run_demo.py
node scripts/console_domain_routing_browser_smoke.js
node scripts/console_domain_browser_smoke.js
node scripts/console_clear_smoke.js
~~~

该专项只验证有界目录、唯一/歧义/无匹配、模型 allowlist/fallback、用户改选、SQLite 重启、共享 HTTP/CLI 入口和 Action Host 状态机。第三 fixture Domain 只证明可替换性；真实 GIS 与 live 模型仍走显式验收，不进入默认 CI。浏览器首次自动请求必须携带未预创建的中立 session identity，选择后才允许读取具体 Domain 的会话和历史。

## M226 路由证据与受控 Model Selector 专项

修改 routing evidence、Result/Async/Artifact/SQLite 边界、Selector provider、跨入口 Harness 或 Console 路由证据展示时，在按当前工作树重建的 Docker 镜像中运行：

~~~powershell
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m224_domain_runtime_host tests.test_m224_domain_persistence tests.test_m224_domain_http tests.test_m225_domain_selector tests.test_m225_domain_routing_persistence tests.test_m225_domain_entrypoints tests.test_m226_domain_routing_application tests.test_m226_domain_routing_evidence_flow tests.test_m226_domain_selector_provider tests.test_m226_routing_evidence_harness -v
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile quick --profile smoke
docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains evaluation production_api.py serve_api.py run_demo.py result_contract.py
node scripts/console_domain_routing_browser_smoke.js
node scripts/console_domain_browser_smoke.js
node scripts/console_clear_smoke.js
~~~

专项比较同一 decision identity 在同步、嵌套 Result、异步 polling、SQLite、artifact 和重启后的稳定 binding，并覆盖 run/idempotency 冲突、未知 schema、脱敏 metrics 和 provider fallback。真实 Model Selector + 本地 GIS 只作为显式 Docker 验收：只记录状态、identity、重试/延迟和 token usage，不保存请求、模型原文、密钥或私有路径；该路径不进入 quick/CI。

## M227 统一 Interaction Contract 专项

修改 interaction 投影、动作 schema、revision/CAS、Result/Async/Artifact/SQLite 迁移、HTTP interaction 入口或 Console Action Host 时，按当前工作树重建 Docker 后运行：

~~~powershell
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --force-recreate
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m227_interaction_contract tests.test_m226_domain_routing_evidence_flow tests.test_m225_domain_entrypoints tests.test_m169_interaction_receipt tests.test_m186_action_precondition_contract -v
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile quick --profile smoke
docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains evaluation production_api.py serve_api.py run_demo.py result_contract.py
node scripts/console_domain_routing_browser_smoke.js
node scripts/console_candidate_selection_browser_smoke.js
node scripts/console_selection_interaction_browser_smoke.js
~~~

三条浏览器脚本必须串行复用 CDP 页面。专项只验证一个 canonical interaction/command/Host seam、三个稳定 HTTP 拒绝码、持久化 journey 和三类代表性 UI 状态；不为每个动作复制测试，也不把真实模型或真实 GIS 加入默认 CI。
