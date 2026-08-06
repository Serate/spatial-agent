# Spatial Agent

面向空间大数据分析的 AI Agent Runtime。

## M1 当前能力

- 使用 Planner 将自然语言需求转换为结构化任务计划。
- 使用 Tool Registry 校验工具参数并分发调用。
- 使用 Agent Runtime 管理计划执行、依赖关系、重试和运行状态。
- 使用确定性的 Demo Spatial Adapter 模拟空间数据工具。
- 对正常任务、缺失信息、越权请求和非法工具参数提供测试。

## M2 当前能力

- 定义 TaskPlan JSON Schema，作为所有 Planner 的输出契约。
- 新增 LLMPlanner，把大模型限制在“生成结构化计划”的 seam 内。
- 新增 OpenAIPlannerClient，可通过 OpenAI Responses API 获取结构化 JSON 计划。
- 保留 RuleBasedPlanner 作为无网络、无 Token 的测试基线。
- 测试使用 fake LLM client，不调用真实模型、不消耗 Token。

## M3 当前能力

- 新增 SpatialBackend 接口，为真实数据接入预留 seam。
- 新增 InMemorySpatialBackend，作为暂时没有真实数据时的稳定占位后端。
- 新增 SpatialToolAdapter，把工具调用转换为后端数据操作。
- 工具结果返回 metrics 和 result_ref，为后续地图渲染、导出和性能对比做准备。

## M4 当前能力

- StepRun 记录 started_at、finished_at 和 latency_ms。
- 新增 evaluation runner，批量运行评测用例并输出 JSON 报告。
- 报告包含状态匹配率、工具序列匹配率、步骤数限制命中率和整体通过率。
- 支持把评测报告写入文件，便于后续做面试展示和回归对比。

## M5 当前能力

- 新增 DatasetProbe，使用 GeoPandas/Rasterio 读取真实矢量和栅格元数据。
- 支持探测 GeoJSON/Shapefile 的 feature 数、字段、几何类型、CRS 和 bounds。
- 支持探测 IMG/TIF 栅格的尺寸、波段数、数据类型、CRS、bounds 和像元大小。
- 保持只读元数据扫描，不加载完整栅格数组，不进行重采样或坡度计算。

## M6 当前能力

- 新增 GeoJSONAdminBackend，真实读取 admin_areas GeoJSON。
- 新增 HybridSpatialBackend，对 admin_areas 使用真实文件，对 roads/slope 保持内存 fallback。
- 支持真实行政区 schema 查询和按 name 字段过滤。
- run_demo 支持 --backend local 切换到本地数据后端。

## M7 当前能力

- RuleBasedPlanner 支持行政区自然语言意图。
- 用户可以输入“查询洪山区行政区边界”，Planner 会生成 admin_areas 的真实 range_query。
- 使用 --backend local 时，Runtime 会真实读取湖北省县级 GeoJSON 并返回匹配行政区。

## M8 当前能力

- 新增 AnswerComposer，把工具执行轨迹转换成面向用户的自然语言答案。
- 行政区查询会展示命中数量、样例名称、CRS、结果引用和本地数据源。
- 通用空间分析答案会保留 result_ref 和命中数量，方便继续接地图渲染或导出流程。

## M9 当前能力

- Runtime 支持按 session_id 保存待澄清请求。
- 当用户先输入“查询行政区边界”再补充“洪山区”时，Agent 会合并上下文并继续执行。
- 澄清上下文按会话隔离，任务完成或被拒绝后会自动清理。

## M10 当前能力

- 新增 AgentService，作为 CLI、HTTP API 或后续前端共用的应用边界。
- 新增 serve_api.py，提供无需额外依赖的 HTTP API。
- POST /runs 支持 request、session_id、planner、backend，并复用 M9 的多轮澄清状态。

## M11 当前能力

- 新增 scripts/smoke_check.py，统一执行核心单元测试和 AgentService 冒烟验证。
- 新增 GitHub Actions CI，在 push 和 pull request 时运行 smoke check。
- 冒烟检查覆盖普通空间查询、缺参数澄清和多轮 follow-up 执行。

## M12 当前能力

- 新增 docs/api.md，说明 HTTP API 契约、请求字段、响应结构和错误响应。
- 补充 /health、/runs 多轮澄清和错误输入的 API 边界测试。
- API 文档提供 PowerShell 调用示例，方便面试或本地演示。

## M13 当前能力

- 新增 Trace Formatter，把 AgentRunResult 转换成可读执行轨迹。
- AgentService 响应新增 trace_summary，展示请求、规划目标、工具调用和最终答案。
- Trace 覆盖 completed、needs clarification 和 rejected 三类状态，方便调试与面试演示。

## M14 当前能力

- 新增 ArtifactStore，可将一次 Agent run 的摘要导出为 JSON artifact。
- AgentService 和 HTTP API 支持 export_artifact=true，并返回 artifact_ref。
- 导出内容只包含 run 摘要、answer 和 trace_summary，不写入原始空间数据。

## M15 当前能力

- 新增 RasterMetadataBackend，使用 Rasterio 读取 DEM 和土地利用栅格的轻量元数据。
- 新增 get_raster_metadata 工具，返回文件数、抽样文件、尺寸、波段数、数据类型、CRS、bounds 和像元大小。
- RuleBasedPlanner 支持“查询DEM栅格元数据”“查询土地利用栅格元数据”等请求。
- local backend 读取真实本地栅格文件；memory backend 返回确定性占位结果，保持离线测试稳定。

## M16 当前能力

- OpenAI Planner 支持从本地 config/openai.local.json 读取 API key、精确 API URL、base URL、模型和 reasoning effort。
- LLM client 支持 Responses API 和 Chat Completions API；DeepSeek 使用 Chat Completions 模式。
- config/openai.local.json 被 Git 忽略；config/openai.example.json 提供可提交的占位模板。
- 默认真实模型配置为 gpt-5.6-luna，reasoning effort 为 medium。
- 对非标准 provider，可用 api_url 精确指定请求地址，并用 auth_location=query 将 key 放到 URL query 参数。
- 保留 RuleBasedPlanner 作为默认路径，CI 和 smoke check 不依赖真实模型 API。
- 新增可选 live smoke test，只有设置 SPATIAL_AGENT_LIVE_OPENAI=1 时才调用真实模型。
- 真实 LLM 请求支持 max_output_tokens、timeout_seconds 和安全的 provider usage metrics。

## M18 当前能力

- `export_geojson=true` 可导出小型 GeoJSON summary。
- summary 只包含工具步骤、状态、耗时、数量、结果引用和 CRS 等白名单字段，不包含原始工具参数或空间数据。
- 导出包含大小限制，当前默认上限为 100 KB；local admin backend 可导出受限真实 geometry，memory/raster 结果保持 geometry 为 null。

## M21 当前能力

- `serve_api.py` 同时提供 Spatial Agent Console 页面。
- 页面支持请求提交、Planner/backend 选择、session、澄清和执行状态展示。
- 页面展示答案、TaskPlan、工具步骤、耗时、planner metrics、trace 和 GeoJSON geometry 预览。
- 页面可直接打开 JSON artifact 和 GeoJSON 导出结果。

## M22 当前能力

- `GET /health` 返回当前服务进程的安全环境状态，包括内存后端、本地 GIS 后端、真实大模型配置、关键 GIS 依赖和数据目录是否可用。
- Console 页面启动后会自动检查运行环境，并在用户选择不可用的本地 GIS 或真实大模型前给出中文提示。
- 新增 `scripts/start_console.ps1`，可用 `-Mode memory` 启动离线演示，用 `-Mode gis` 从 `spatial-agent-gis` 环境启动真实本地 GIS 演示。

## M23 当前能力

- Console 采用中文对话式交互，用户可以像聊天一样连续输入空间分析问题。
- 对话区保留同一个 session_id，可支持行政区名称补充等多轮澄清流程。
- 页面仍同步更新分析结论、规划指标、任务步骤、执行轨迹、空间预览和 artifact 链接，便于展示 Agent 内部执行过程。
- 内置 DEM、行政区、土地利用示例问题，方便本地演示时快速发起请求。

## M24 当前能力

- 新增 `get_raster_statistics` 工具，使用 Rasterio 分块读取真实栅格像元。
- DEM/土地利用统计默认最多分析 3 个文件，返回最小值、最大值、平均值、标准差、有效像元数和 NoData 比例。
- 规则规划器支持“分析 DEM 高程统计”等请求；真实 LLM 也可以选择该工具。
- Console 新增“栅格统计指标”面板，直接展示统计结果，不只依赖自然语言答案。

## M25 当前能力

- 新增 `get_zonal_raster_statistics` 工具，按行政区名称查询边界、转换坐标系并用 Rasterio mask 计算区域内栅格统计。
- 支持“分析洪山区 DEM 高程概况”等自然语言请求，返回区域最小值、最大值、均值、标准差、有效像元和 NoData 比例。
- 当行政区不存在或与当前栅格文件没有交集时，返回明确的业务结论，不伪造统计值。

## M26 当前能力

- Console 的栅格统计面板升级为“统计概览”，显示区域/数据集、分析文件数、最小值—最大值范围和均值位置。
- 新增有效像元覆盖条和 NoData 比例展示，让真实栅格结果的覆盖质量可以直接在对话页面判断。
- 统计结果缺失、无交集或工具报错时保留明确空态，不显示误导性的默认数值。

## M27 当前能力

- 栅格统计结果增加受限样本值分布摘要，默认生成 10 个值域桶，不加载完整栅格到内存。
- Console 在统计概览中显示原生 CSS 分布条形图，并标注样本数，明确这是分布样本而非完整像元直方图。

## M28 当前能力

- Console 支持“新建会话”和“清空对话”，可以在不刷新页面的情况下切换演示上下文或重新开始。
- 新建会话会生成新的 `session_id`，与服务端多轮澄清状态隔离；清空对话只清理当前页面展示。

## M29 当前能力

- 增加可选的真实模型端到端测试，验证模型规划、GIS 工具执行和区域 DEM 结果可以串联完成。
- 该测试仅在显式设置 `SPATIAL_AGENT_LIVE_OPENAI=1` 时运行，不进入默认 CI，也不会让离线测试消耗 Token。

## M30 当前能力

- Console 的每个工具步骤显示关键结果摘要，包括命中数量、栅格统计均值、有效像元和 NoData 比例。
- 工具执行失败时在对应步骤显示业务错误，便于区分“工具已执行但无结果”和“没有执行工具”。

## M31 当前能力

- 栅格统计结果返回分析文件的合并 bounds 和 CRS。
- Console 在没有 GeoJSON 几何导出时显示栅格覆盖范围预览，DEM 分析也具备空间上下文。

## 本地运行

需要 Python 3.10 或更高版本。不需要第三方依赖。

~~~powershell
python run_demo.py "查询距离主干道500米以内、坡度超过25度的区域。"
~~~

使用本地数据后端：

~~~powershell
python run_demo.py --backend local "查询距离主干道500米以内、坡度超过25度的区域。"
python run_demo.py --backend local "查询洪山区行政区边界"
python run_demo.py --backend local "查询DEM栅格元数据"
python run_demo.py --backend local "查询土地利用栅格元数据"
~~~

使用 OpenAI Planner：

~~~powershell
copy config\openai.example.json config\openai.local.json
# 编辑 config\openai.local.json，填入本地 API key、api_url 或 base_url、model 和 model_reasoning_effort。
python run_demo.py --planner openai "查询距离主干道500米以内、坡度超过25度的区域。"
python run_demo.py --planner openai "查询DEM栅格元数据"
~~~

查看运行 artifact：

~~~powershell
# 先通过 POST /runs 并设置 export_artifact=true 生成 JSON artifact
python view_artifact.py outputs\runs\<run-id>.json
~~~

viewer 只展示运行摘要、计划目标、工具状态、耗时、结果引用和 trace，不导出原始空间数据或工具参数。

通过 HTTP API 导出 GeoJSON summary：

~~~powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8088/runs `
  -ContentType "application/json" `
  -Body '{"request":"查询DEM栅格元数据","export_geojson":true}'
~~~

启动中文 Console：

~~~powershell
scripts\start_console.ps1 -Mode memory -Port 8088
scripts\start_console.ps1 -Mode gis -Port 8088
~~~

`memory` 模式适合离线演示和 CI 级别验证；`gis` 模式需要本机存在 `spatial-agent-gis` conda 环境，并安装 GeoPandas 与 Rasterio。真实大模型还需要 `config/openai.local.json` 或环境变量提供 provider 配置。

也可以用环境变量覆盖本地配置：

~~~powershell
$env:OPENAI_API_KEY="sk-your-key"
$env:OPENAI_API_URL="https://api.openai.com/v1/responses"
$env:OPENAI_BASE_URL="https://api.openai.com"
$env:OPENAI_MODEL="gpt-5.6-luna"
$env:OPENAI_REASONING_EFFORT="medium"
python run_demo.py --planner openai "查询DEM栅格元数据"
~~~

使用 DeepSeek Chat Completions：

~~~powershell
$env:OPENAI_API_KEY="your-deepseek-key"
$env:OPENAI_BASE_URL="https://api.deepseek.com"
$env:OPENAI_WIRE_API="chat_completions"
$env:OPENAI_MODEL="deepseek-v4-flash"
python run_demo.py --planner openai "查询DEM栅格元数据"
~~~

运行测试：

~~~powershell
python -m unittest discover -s tests -v
~~~

运行评测：

~~~powershell
python run_evaluation.py
python run_evaluation.py --output evaluation/reports/latest.json
~~~

创建 GIS 环境：

~~~powershell
conda env create -f environment.yml
conda activate spatial-agent-gis
~~~

检查本地数据目录：

~~~powershell
python inspect_datasets.py
python probe_datasets.py --max-files 2
python probe_datasets.py --max-files 2 --output evaluation/reports/dataset-metadata.json
~~~

## 当前架构

~~~text
request
  -> Planner Adapter
  -> TaskPlan
  -> AgentRuntime
  -> ToolRegistry
  -> Spatial Adapter
  -> AgentRunResult
~~~

M1 使用 RuleBasedPlanner 和 DemoSpatialAdapter 作为可替换 Adapter。M2 增加 LLMPlanner 和 OpenAIPlannerClient。接入真实大模型时，只替换 Planner Adapter；接入 GeoPandas、PostGIS、Spark 或 HBase 时，只替换工具 Adapter。

## 项目文档

- docs/spatial-agent-design.md：完整系统设计。
- docs/m0-scope.md：M0 场景与验收范围。
- docs/data-adapter-plan.md：真实空间数据接入计划。
- tools/schema/tool-definitions.json：工具输入输出契约。
- evaluation/cases/m0-cases.json：评测用例。
- config/datasets.local.example.json：本地数据目录示例配置。
