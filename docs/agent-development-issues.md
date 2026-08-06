# Agent 开发问题记录

本文档记录 Spatial Agent 开发过程中遇到的实际问题。它是项目级记录，不属于某个特定里程碑。每当出现新的 Agent 工程问题时，都应在依赖对话记忆之前更新本文档。

## 更新规则

每个问题都记录以下内容：

1. 现象：什么失败了，或什么行为看起来不正确。
2. 根因：实际导致问题的原因。
3. 诊断：下次最快确认问题的方法。
4. 修复：解决问题所采用的实现或流程改动。
5. 预防：减少问题再次发生的测试、提示词规则、schema 规则、配置规则或文档规则。

不得记录密钥、原始数据或 provider 返回的私有内容。

## Planner 输出结构漂移

### 现象

LLM Planner 可能返回合理的工具调用，但不符合要求的 TaskPlan 结构。

曾观察到的 live 输出：

~~~json
{
  "outcome": "success",
  "tool": "get_raster_metadata",
  "args": {
    "dataset": "dem",
    "max_files": 3
  }
}
~~~

要求的结构：

~~~json
{
  "goal": "inspect raster dataset metadata",
  "steps": [
    {
      "id": "raster-metadata",
      "tool": "get_raster_metadata",
      "args": {
        "dataset": "dem",
        "max_files": 3
      },
      "depends_on": []
    }
  ],
  "output": {
    "type": "raster_metadata_result",
    "summary": true
  }
}
~~~

### 根因

模型理解了工具意图，却把计划压缩成了快捷结构。结构化输出有帮助，但仍需要由提示词和解析器共同约束运行时契约。

### 诊断

直接调用 planner client，在 TaskPlan 解析之前检查原始 JSON。确认是否包含 goal 和 steps。

### 修复

收紧 planner 提示词，要求成功计划必须使用 goal、steps 和 output。同时在解析前将已知的单工具快捷结构归一化为 TaskPlan，并继续保留 ToolRegistry 作为最终执行边界。

### 预防

测试完整 TaskPlan、拒绝结果、澄清结果和快捷结构结果。

## Chat Completions 工具参数字段漂移

### 现象

真实模型可以生成正确的行政区查询意图，但返回的 range_query 参数使用 field、value 这样的简写，缺少工具契约要求的 conditions 和 limit。运行时最终报错：missing required fields: conditions, limit。

### 根因

Chat Completions 的 JSON object 模式只能保证返回 JSON，不能保证每个工具参数符合工具 schema。当前 planner prompt 只描述了“按名称查询”，没有把 range_query 的完整参数形状写出来。

### 诊断

检查失败 run 的 plan 和步骤参数。如果工具名称正确但参数含有 field/value、缺少 conditions/limit，说明是模型输出字段漂移，不是 GeoPandas、Rasterio 或数据文件失败。

### 修复

在 planner guidance 中加入完整的 range_query 参数模板，并在 TaskPlan 解析前将已知的 field/value 简写转换为 conditions=[{field, operator, value}]，缺少 limit 时补充默认上限 100。最终仍由 ToolRegistry 执行 schema 校验。

### 预防

每个真实模型新增工具场景都要测试完整参数、字段简写和缺字段输出。Chat Completions 不能只测试 JSON 可解析，还必须测试工具参数归一化和最终 backend 执行。

## Chat Completions 的结构化输出约束不足

### 现象

DeepSeek Chat Completions 请求可以正常返回 JSON，但 Runtime 可能因为模型返回的 TaskPlan 字段类型不稳定而失败，例如 `steps` 元素不是对象，或 `output` 返回字符串，最终出现 `step 0 must be an object` 等解析错误。

### 根因

Responses API 可以通过 `json_schema` 和 `strict` 直接约束输出；Chat Completions 兼容模式只使用 `response_format: {"type":"json_object"}` 时，通常只能保证结果是 JSON，不能保证 JSON 符合 TaskPlan schema。

### 诊断

先确认 HTTP 请求成功，再检查返回 JSON 的顶层字段、`steps` 的类型及每个元素的类型、`output` 的类型。不要把 Chat Completions 的 JSON 解析成功误认为 TaskPlan 校验成功。

### 修复

在 system prompt 中直接写出完整 TaskPlan 成功结构，明确要求 `steps` 必须是对象数组、`output` 必须是对象。对无歧义的字符串 output 做 `{"type": value}` 归一化；steps、tool、args 和依赖关系仍交给 TaskPlan parser 与 ToolRegistry 严格校验。

### 预防

不同 wire API 必须分别测试：Responses 测试 schema 约束，Chat Completions 测试 prompt 约束、字段类型漂移、未知工具和真实 live smoke。不能因为 provider 宣称 OpenAI 兼容，就假设两种协议的结构化输出能力相同。

## Planner 领域词汇缺口

### 现象

用户请求查询 DEM 栅格元数据时，live planner 要求用户提供 DEM dataset 名称。

### 根因

模型不知道用户表达的领域术语与内部 dataset ID 之间的映射关系。

### 诊断

如果一个本应可执行的请求返回 NEEDS_CLARIFICATION，则检查澄清文本。如果模型要求用户提供实际上已经由用户请求隐含的信息，说明 planner guidance 缺少领域映射。

### 修复

在 planner guidance 中记录用户术语到 dataset ID 的映射。

| 用户术语 | 内部 dataset |
|---|---|
| DEM / 高程 / 地形栅格 | dem |
| 土地利用 / land use 栅格 | land_use |
| 行政区 / 边界 / 县区 | admin_areas |

### 预防

新增 dataset 或工具时，同时加入面向用户的同义词和领域术语。

## Tool Registry 契约扩展

### 现象

新增工具后，旧测试失败，因为测试断言了固定的工具数量或固定的历史工具集合。

### 根因

早期测试把某个里程碑的 Registry 结构错误地当成了永久契约。

### 诊断

失败信息中出现意外工具名称，例如 `get_raster_metadata`。

### 修复

让测试断言当前注册的工具集合；如果工具集合本身不是契约，则改为断言基础工具仍然存在。

### 预防

新增工具时，同时更新 schema、adapter dispatch、memory/local backend 行为、测试和 smoke check。

## 必须进行分层校验

### 现象

Planner 生成的 JSON 看起来有效，但运行时因为 dataset、field、operator、dependency 或 output type 错误而失败。

### 根因

仅校验 JSON 结构不足以保证 Agent 正确性。

### 诊断

按校验层级分类失败：

- PlanningError：Planner 输出结构错误或包含未知工具。
- ToolError：ToolRegistry 校验失败或 backend 执行失败。
- NEEDS_CLARIFICATION：Planner 选择暂停并向用户澄清。
- FAILED 且包含步骤错误：运行时已进入工具执行阶段，但工具执行失败。

### 修复

保留分层校验：模型 schema、TaskPlan 解析、运行时依赖检查、ToolRegistry 输入 schema、backend 校验。

### 预防

绝不能绕过 ToolRegistry 执行 LLM 生成的计划。

## 真实模型 API 与确定性测试不同

### 现象

Fake client 测试通过，但真实模型执行出现 provider 错误、澄清、格式错误的计划或错误的工具选择。

### 根因

Fake client 只能验证解析器行为，不能证明真实模型输出符合约定，也不能证明 provider 兼容性、认证、网络和提示词鲁棒性。

### 诊断

将失败分为 provider/network/auth、模型输出解析、计划校验和工具执行四类。

### 修复

保留 Fake 测试以支持 CI，并增加默认关闭的可选 live smoke test。

### 预防

Live 测试默认必须跳过。只有手动验证 provider 时才设置 `SPATIAL_AGENT_LIVE_OPENAI=1`。

## Provider 的 HTTP 行为可能不同于 Codex

### 现象

同一个模型 provider 在 Codex 中可用，但项目的 Python client 请求失败。

已观察到的行为：

- Python urllib 的默认请求返回 HTTP 403，错误码为 1010。
- 添加普通 User-Agent 和 Accept: application/json 后，provider 返回 HTTP 200。

### 根因

Codex 可能设置了不同的 headers，使用了不同的运行时 client，或经过了不同的网络路径。Python 脚本不会自动继承这些请求细节。

### 诊断

对比 Codex provider 配置、环境变量、不同 User-Agent 下的 HTTP 状态，以及响应是否已经到达模型层 JSON。

### 修复

显式设置 client headers：

~~~text
Accept: application/json
Content-Type: application/json
User-Agent: spatial-agent/0.1
Authorization: Bearer <key>
~~~

### 预防

如果 live API 在模型输出之前返回 403，应先检查 headers 和网络，再修改 planner 逻辑。

## Live Provider 读取超时

### 现象

请求已经进入真实 provider，但 live smoke 在等待响应时超时，Runtime 返回 FAILED，未产生 TaskPlan。

### 根因

provider 没有在 client 设置的读取超时时间内返回响应。该失败发生在模型输出、TaskPlan 解析和 backend 执行之前。

### 诊断

检查 Runtime 的错误是否为读取超时，并确认没有出现 HTTP 状态码、模型 JSON 或步骤执行信息。使用显式开启的 live smoke 单独复现，不要用离线测试判断 provider 可用性。

### 修复

将底层 `TimeoutError` 包装为明确的 `PlanningError("OpenAI request timed out")`，让 trace 能区分 provider 超时与计划校验失败。

### 预防

Live smoke 默认保持关闭；执行时记录 provider 请求是否完成，但不得记录 API key 或完整私有响应。必要时再根据 provider 稳定性调整 client timeout 或增加可配置的超时参数。

## Provider URL 和认证形式必须明确

### 现象

OpenAI 兼容的 base_url、完整 api_url、header auth 和 query-string key auth 之间容易产生混淆。

### 根因

不同 provider 使用不同约定。在一个工具中有效的 URL/key 组合，不能证明另一个 client 使用了正确的协议形式。

### 诊断

确认 provider 的实际 endpoint URL、请求 body 结构、key 的位置、参数名和响应 body 结构。

### 修复

对 OpenAI 兼容 Responses client 支持 base_url；对完整 endpoint provider 支持 api_url；认证支持 header 或 query 两种位置。

### 预防

provider 文档给出完整 URL 时不要猜 endpoint 后缀。除非 provider 明确要求，否则不要切换到 query auth。

## 前端选择项必须反映服务端真实能力

### 现象

Console 前端可以选择“本地 GIS”或“真实大模型”，但服务端进程可能并没有运行在 GIS conda 环境，或没有可用的大模型配置。用户点击“开始分析”后才看到 backend 报错，例如 `rasterio is required for RasterMetadataBackend`，容易误以为工具已经执行但没有真实结果。

### 根因

前端的 planner/backend 下拉选项是静态展示，之前没有读取当前服务进程的 Python 环境、GIS 依赖、数据目录和 LLM 配置状态。浏览器页面可用不代表服务端具备对应能力。

### 诊断

先访问 `GET /health`，检查：

- `capabilities.local_gis_backend` 是否为 true。
- `dependencies.rasterio` 和 `dependencies.geopandas` 是否为 true。
- `data.dataset_root_exists` 是否为 true。
- `capabilities.live_llm` 是否为 true。

如果 local GIS 为 false，但页面选择了本地 GIS，问题在服务启动环境，不在栅格工具本身。

### 修复

`GET /health` 返回安全的运行环境能力信息。Console 页面启动后自动读取该接口，并在选择不可用能力时提前阻止执行，提示用户用正确模式启动服务。

### 预防

新增运行模式或外部依赖时，必须同时更新：

- health capability 字段。
- Console 前置校验。
- API 契约测试。
- README 启动说明。

## 中转 Provider 与 Codex 调用链不一致

### 现象

同一个中转地址在 Codex 中可以调用，但项目 Python client 先返回 HTTP 403/error code 1010；补充普通 User-Agent 和 Accept header 后，基础 endpoint 探测可以返回 HTTP 200，但真实模型 POST 请求在 `/responses`、`/v1/responses` 以及 `/v1/chat/completions` 都发生读取超时。

### 根因

中转地址只是网关入口，Codex 和项目 client 可能使用不同的 endpoint、协议细节、streaming 设置、请求 headers、代理链、超时重试策略或认证凭据。Codex 配置中的 `wire_api=responses` 不能证明 Python 请求体和完整调用链完全相同。网关能返回 200 也不能证明模型上游已经成功处理请求。

### 诊断

按层级验证：先用无认证基础请求确认网络和网关，再用最小模型 POST 区分路由和模型上游，最后再加入 reasoning、JSON schema 和项目 prompt。分别记录 HTTP 状态、响应是否完成、响应解析和 TaskPlan 校验结果。不要输出 API key 或完整私有响应。

### 修复

项目 client 显式设置 Accept、Content-Type、User-Agent 和 Bearer header，并支持 `base_url`、精确 `api_url`、Responses/Chat Completions 两种 wire API 及可选 query auth。中转 provider 未确认模型 POST 兼容前，保留 RuleBasedPlanner 和已验证的 DeepSeek Chat Completions 作为可用路径，不让 CI 依赖中转服务。

### 预防

把“Codex 可用”和“项目 API client 可用”作为两个独立验收条件。接入新的中转站时，必须完成最小模型请求、真实 TaskPlan smoke 和错误分类；不能只依据根 URL 可达、探活 200 或 Codex 配置推断兼容。

## 服务进程网络权限导致 WinError 10013

### 现象

通过本地 Console 调用真实 Planner 时，API 返回 `OpenAI request failed: <urlopen error [WinError 10013]>`；同一份配置和请求在允许出站网络的进程中可以正常完成。

### 根因

`serve_api.py` 进程继承了启动环境的 socket 权限限制。HTTP 页面和本地 `/runs` 路由仍然可用，但该 Python 进程不能向外部 provider 建立连接。

### 诊断

先通过本地 API 复现 `planner=openai` 请求，再在同一端口只更换服务进程的网络权限。若错误从 WinError 10013 变为 COMPLETED，说明是服务进程运行环境，而不是 API key、模型或 TaskPlan。

### 修复

停止受限的服务进程，并在允许出站网络的终端重新启动 `serve_api.py`。本次重启后 DeepSeek live 请求返回 COMPLETED。

### 预防

真实模型演示必须从允许访问 provider 的普通终端启动 API 服务；CI 和默认 smoke 继续使用离线 RuleBasedPlanner。遇到 WinError 10013 时先检查进程权限，不要修改请求协议或轮换 key。

## GIS 依赖和本地数据可用性

### 现象

GIS 测试会根据 Python 环境和本地数据是否存在而失败或跳过。

### 根因

默认 Python 可能没有 geopandas 或 rasterio。原始 GIS 数据位于仓库外，不能提交到仓库。

### 诊断

检查 geopandas/rasterio 是否可以导入，并检查 `D:/dataset/agent` 是否存在。

### 修复

为 GIS 专用测试增加 skip guard，并保留确定性的 memory backend 测试以支持 CI。

### 预防

不要让 CI 依赖本地原始 GIS 数据。

## 前端选择 Local GIS 不会改变服务 Python 环境

### 现象

Console 中选择“本地 GIS”并查询 DEM 栅格元数据时，返回 `rasterio is required for RasterMetadataBackend`。

### 根因

前端的 backend 选择只改变 `/runs` 请求参数；它不会切换已经启动的 `serve_api.py` 进程环境。若服务进程由普通 Python 启动，则缺少 rasterio/geopandas，即使请求参数是 `backend=local` 也无法读取真实 GIS 数据。

### 诊断

用同一个 `/runs` 请求做对照：普通 Python 服务返回 rasterio 缺失；用 `spatial-agent-gis` conda 环境重启服务后，同一请求返回真实 DEM 元数据。

### 修复

停止普通 Python 启动的 8088 服务，并用 `conda run -n spatial-agent-gis python serve_api.py --host 127.0.0.1 --port 8088` 重启。真实 DEM 查询返回 9 个文件、抽样 3 个文件、尺寸、CRS、像元大小和范围。

### 预防

本地 GIS 演示必须从 GIS conda 环境启动服务；前端只负责选择 backend，不负责安装或切换 Python 依赖。

## 栅格元数据范围蔓延

### 现象

栅格功能请求容易从元数据查询扩展到裁剪、重采样、坡度计算或大规模数组读取。

### 根因

栅格数据通常很大，真实地理计算可能变慢，并引入较重的依赖。

### 诊断

确认任务只需要元数据，还是确实需要像素处理。

### 修复

对于元数据里程碑，只读取文件数量、样本文件、尺寸、波段数、dtype、CRS、边界和像元大小。

### 预防

除非里程碑明确要求栅格计算，否则不要读取完整栅格数组。

## AnswerComposer 可能隐藏有用的 trace 数据

### 现象

Runtime 成功完成，但面向用户的答案遗漏了工具输出中的有用细节。

### 根因

工具结果面向机器结构化，而用户答案需要显式的组合逻辑。

### 诊断

对比结果步骤和最终答案。

### 修复

为新增结果类型加入对应的答案组合分支。

### 预防

新增工具输出类型时，同时增加 planner output type、AnswerComposer 分支、trace 预期，以及用户可见场景所需的 service/API 覆盖。

## 多轮澄清状态

### 现象

后续回答可能在没有待处理请求的情况下被解释，或者澄清状态泄漏到其他 session。

### 根因

澄清状态必须按 session_id 隔离，并在正确时机清理。

### 诊断

测试以下场景：含糊请求、同一 session 的后续回答、另一 session 的无关请求，以及完成或拒绝后的状态清理。

### 修复

使用以 session_id 为键的会话存储。

### 预防

每个澄清功能都必须测试 session 隔离和清理。

## Artifact 导出安全

### 现象

导出 Agent artifact 时，可能意外包含原始数据、大型几何对象、本地密钥或 provider 配置。

### 根因

Agent trace 通常包含工具参数、文件路径和模型输出。

### 诊断

在提交或分享前检查导出的 JSON。

### 修复

只导出紧凑的运行摘要：运行元数据、答案、trace 摘要和结果引用。

### 预防

保持 outputs 目录被 Git 忽略。不要导出原始空间数据或凭据。

## Geometry 导出必须与普通运行结果隔离

### 现象

普通工具结果只包含 `result_ref`、数量和指标，无法直接生成真实地图 geometry；如果把 geometry 直接放进每次 Runtime 响应，可能导致响应过大并暴露原始空间数据。

### 根因

运行结果、trace 和 artifact 面向调试与交互，geometry 导出面向明确的下游地图用途，两者的数据安全和大小约束不同。

### 诊断

检查普通 `/runs` 响应是否只包含结果引用和统计信息，并单独验证 `export_geojson=true` 是否经过 feature 数量和文件大小限制。

### 修复

将 geometry 导出放在显式的 result export 链路中。GeoJSON backend 只缓存受限查询结果，在导出时生成白名单属性和最多指定数量的 Feature；memory/raster backend 没有 geometry 时返回空 FeatureCollection 或 null geometry summary。

### 预防

不要为了方便把 geometry 加入所有工具结果、trace 或 artifact。新增 geometry backend 时，必须测试字段白名单、最大 feature 数、最大文件大小和默认响应不包含原始 geometry。

## 文档漂移

### 现象

README、API 文档、交接文档和测试对某个里程碑支持的能力描述不一致。

### 根因

Agent 项目会同时演进多个边界：planner、registry、backend、AnswerComposer、service 和 artifact。

### 诊断

每个里程碑完成后，对比 README、API 文档、task-resume 文档、测试和工具 schema。

### 修复

在同一个变更中同步更新文档。

### 预防

今后出现新的 Agent 开发问题时，应在本文件中优先记录，或至少与修复放在同一个 patch 中。

## 配置存在但服务进程无法访问模型网络

### 现象

Console 的环境状态显示真实大模型配置可用，但发送请求后返回 OpenAI request failed: WinError 10013。GIS 后端和本地规则规划器仍然可以正常工作。

### 根因

之前的 health 检查只根据 API key 或本地配置文件是否存在判断 live_llm=true，没有判断当前服务进程是否能建立出站 socket。受限制的启动终端可以正常提供页面和本地 GIS，但不能访问外部模型 provider。

### 诊断

用最小的 planner=openai 请求复现，并检查响应中的 planner_metrics.error_type 是否为 url_error。再访问 /health，区分 live_llm_configured=false（没有模型配置）与 live_llm_configured=true 且 live_llm_network=false（服务进程网络受限）。

### 修复

health 检查对配置 provider 主机执行不发送模型请求的短 TCP 探测，并新增 live_llm_configured、live_llm_network 字段。Console 在发送前拦截网络受限状态，提示从允许出站网络的终端重新启动服务。

### 预防

不能把“配置文件存在”当成“真实模型可用”。真实模型能力必须同时检查配置、网络权限和后续 live smoke；离线规则规划器仍作为无网络环境下的可用回退路径。

## 行政区与栅格联动必须处理 CRS 和无交集

### 现象

行政区边界通常使用地理坐标系，而 DEM 可能使用 UTM 投影。直接将行政区坐标传给 Rasterio mask 会得到错误统计或抛出无交集异常；即使坐标转换正确，所选行政区也可能确实不覆盖当前栅格文件。

### 根因

向量和栅格数据各自保留了原始 CRS，不能假设两者相同。区域统计还需要把“不存在行政区”“存在但无栅格交集”和“有有效像元”区分为不同业务结果。

### 诊断

检查行政区 geometry 的 CRS、每个栅格文件的 CRS、mask 后的有效像元数和匹配文件数。不要只根据文件存在或 geometry 查询成功就认为能生成区域统计。

### 修复

区域栅格统计工具在每个栅格文件上使用 Rasterio transform_geom 转换行政区 geometry，再用 mask 计算统计；没有有效像元时返回明确的 no raster pixels intersected 业务结果。

### 预防

新增 vector-raster 联动功能时，必须测试 CRS 转换、真实有交集区域和无交集区域三种情况，并在答案中说明结果范围受当前本地栅格覆盖限制。

## 大型栅格分布图不能直接暴露像元数组

### 现象

前端需要展示 DEM 或土地利用值分布，但完整栅格数组可能非常大，直接返回会增加内存、响应体和浏览器渲染压力。

### 根因

栅格统计 API 的职责是返回可控的分析摘要，而不是把原始像元数据传给 UI。完整直方图还可能需要额外的全量扫描。

### 诊断

检查统计工具是否在单次请求中加载完整数组，或响应中是否出现大规模像元列表。确认前端只需要趋势展示，不需要逐像元查询。

### 修复

统计过程继续按 Rasterio block 分块读取，只保留最多 10,000 个有效值样本，并据全局最小值和最大值生成 10 个分布桶。响应明确标记 `sampled=true` 和 `sample_count`，前端将其显示为受限样本分布图。

### 预防

大栅格可视化默认使用摘要、采样或瓦片服务；不要把原始像元数组放入 Agent 答案、trace、artifact 或普通 HTTP 响应。

## 真实模型验收必须覆盖工具执行

### 现象

真实模型能够返回可解析 JSON，并不代表它选择了正确工具，也不代表 GIS 后端能完成该工具调用。

### 根因

模型响应、TaskPlan 校验、工具 dispatch 和本地 GIS 依赖属于不同边界。只测试 planner 输出会遗漏后续执行失败。

### 诊断

用一个明确的领域请求执行完整 Runtime，分别检查最终状态、工具名称、工具结果中的业务错误和用户答案；不要只断言 HTTP 200 或 JSON 可解析。

### 修复

增加默认跳过的 live zonal smoke，验证“分析洪山区 DEM 高程概况”能生成 `get_zonal_raster_statistics`，在 GIS 后端产生有效像元，并在答案中包含区域信息。

### 预防

每新增一个真实模型可调用的领域工具，至少增加一个显式 opt-in 的端到端 smoke；离线 CI 继续使用 fake client 和规则规划器。

## 执行轨迹不能只展示生命周期状态

### 现象

前端轨迹显示工具已经完成，但用户看不到工具返回的统计值、命中数量或业务错误，容易误以为没有实际结果。

### 根因

早期步骤组件只渲染工具名、状态、耗时和尝试次数；这些字段能说明执行过程，却不能说明工具产出了什么。

### 诊断

对比 API `steps[].result` 与前端步骤卡片。如果响应中有结构化结果而页面只有“completed”，说明是展示层信息丢失，不是 Runtime 或 backend 没有返回结果。

### 修复

新增步骤结果摘要，根据工具类型展示命中数量、结果引用、栅格均值、有效像元、NoData 比例和业务错误；原始大对象仍不直接嵌入页面。

### 预防

新增工具时同时定义用户可读的结果摘要，并测试 Console 至少能展示成功结果和失败结果的关键信息。

## 计划依赖不能指向后续步骤

### 现象

计划的 `depends_on` 中声明了一个位于当前步骤之后的步骤。计划结构表面上合法，但执行时只能在运行阶段发现依赖未完成，错误信息不够靠近规划边界。

### 根因

依赖存在性校验和依赖顺序校验被分开处理，早期只检查依赖 ID 是否存在，没有检查步骤位置。

### 修复

Runtime 计划校验现在要求所有依赖必须位于当前步骤之前；结果引用仍同时要求来源写入 `depends_on`，并由 schema 校验引用格式、来源和顺序。

### 预防

多步骤计划测试必须覆盖未知依赖、越序依赖、悬空结果引用和合法绑定；不要把越序问题留给执行阶段处理。

## 整数 DEM 重投影时不能直接填充 NaN

### 现象

建设适宜性分析在土地利用栅格与 DEM 对齐阶段失败，错误为 `Cannot convert fill_value nan to dtype int16`。普通 DEM 元数据和单独坡度统计仍可能正常。

### 根因

ASTER DEM 常用 `int16` 存储。Rasterio 返回的 masked 整数数组不能直接使用 `filled(numpy.nan)`，因为 NaN 不是整数类型可表示的值。

### 修复

在重投影前将 DEM masked array 显式转换为 `float32`，再填充 NaN 并进行双线性重采样；结果计算继续通过有限值掩膜控制有效像元。

### 预防

凡是需要 NoData/NaN、梯度或重采样的栅格计算，都必须显式处理整数 dtype、浮点 dtype 和 masked array，不能只用元数据读取测试代替真实像元计算测试。

## 栅格任务误用内存后端会返回占位结果

### 现象

用户请求建设适宜性或 DEM 分析后，答案显示 `in-memory backend has no raster geometry`、`no DEM pixels` 或 `no aligned DEM and land-use pixels`，但页面看起来像任务已完成。

### 根因

内存后端用于离线确定性测试，只提供占位结果；前端允许用户在需要真实栅格像元的任务中保持“内存演示”选择，导致业务错误混入正常答案。

### 修复

建设适宜性、DEM、坡度和土地利用请求在 Console 发送前要求选择“本地 GIS”；内存后端答案明确说明未读取真实栅格，并给出切换提示。

### 预防

前端选择项必须依据任务能力做校验；测试和文档要区分“规则规划器可运行”和“真实 GIS 像元已读取”。

## 真实候选几何可能超过 GeoJSON 摘要大小上限

### 现象

建设适宜性分析本身已经成功，但开启 GeoJSON 导出后返回 `GeoJSON summary exceeds max_bytes`，用户无法看到文字结果。

### 根因

候选栅格矢量化后可能包含大量面要素和坐标，直接把所有几何写入固定大小的运行摘要会超过响应/文件上限。

### 修复

GeoJSON 导出器按序列化后的实际大小逐个保留要素，超限时截断并设置 `geometry_truncated=true`；普通运行响应只保留 `result_ref`，不嵌入候选几何。

### 预防

空间导出必须同时限制要素数量、文件大小和几何内容；超限应返回可解释的截断结果，不能让已完成的分析整体失败。

## 多步骤结果引用必须与依赖声明一致

### 现象

多步骤计划可能在参数中引用前一步结果，但没有声明 `depends_on`，或者引用不存在、尚未执行的步骤。

### 根因

步骤依赖和参数引用如果由不同逻辑分别处理，计划看起来结构正确，却可能在执行时读取不到结果，甚至产生越序执行。

### 诊断

解析计划时递归检查参数中的 `$from/path` 对象，核对来源步骤是否存在、是否在 `depends_on` 中、是否位于当前步骤之前。

### 修复

统一结果引用格式为 `{"$from":"步骤ID","path":"结果字段"}`，在计划解析阶段拒绝悬空、越序和格式不完整的引用；Runtime 只从已完成步骤结果中解析路径。

### 预防

多步骤工具测试同时覆盖合法绑定、缺少依赖、未知来源、未知字段和循环/越序引用，不能只测试 `depends_on` 数组本身。

## scripts 子目录直接执行会丢失仓库模块路径

### 现象

直接运行 `python scripts/evaluate_planner.py` 时，Python 报找不到仓库内的 `evaluation` 模块；从仓库根目录导入同一模块却正常。

### 根因

Python 直接执行脚本时会优先把脚本所在的 `scripts` 目录放入模块搜索路径，不会自动把仓库根目录加入 `sys.path`。

### 诊断

分别用 `python scripts/xxx.py` 和 `python -m package.module` 执行入口。如果只有前者失败，检查脚本是否依赖仓库根目录下的包。

### 修复

脚本入口根据 `__file__` 计算仓库根目录并显式加入 `sys.path`，保持从任意当前目录调用时都能加载项目模块。

### 预防

新增 scripts 入口时至少测试一次直接路径执行，并避免依赖用户当前工作目录；若适合，也提供等价的模块执行方式。

## 取消和超时不能强杀第三方 GIS/模型调用

### 现象

用户希望立即停止运行，但当前工具可能正在 Rasterio 读取或等待模型 provider；强制终止线程可能留下半完成状态或破坏外部库内部资源。

### 根因

Python 线程和第三方调用没有安全的通用强杀机制。Runtime 只能可靠地控制自己的步骤调度边界。

### 诊断

区分“取消请求已登记”和“当前工具已经返回”。如果取消后当前调用仍短暂运行，但下一步骤没有启动，说明协作式取消正常工作。

### 修复

采用协作式控制：取消在安全边界收敛为 `CANCELLED`，超时收敛为 `TIMED_OUT`；已完成结果保留，后续步骤标记 `BLOCKED`。

### 预防

API 文档必须说明取消不是强杀；工具实现应尽量使用可配置的 provider、网络和文件读取超时，并在步骤边界检查取消/超时状态。

## 取消和超时不能强杀第三方 GIS/模型调用

### 现象

用户希望立即停止运行，但当前工具可能正在 Rasterio 读取或等待模型 provider；强制终止线程可能留下半完成状态或破坏外部库内部资源。

### 根因

Python 线程和第三方调用没有安全的通用强杀机制。Runtime 只能可靠地控制自己的步骤调度边界。

### 诊断

区分“取消请求已登记”和“当前工具已经返回”。如果取消后当前调用仍短暂运行，但下一步骤没有启动，说明协作式取消正常工作。

### 修复

采用协作式控制：取消在安全边界收敛为 `CANCELLED`，超时收敛为 `TIMED_OUT`；已完成结果保留，后续步骤标记 `BLOCKED`。

### 预防

API 文档必须说明取消不是强杀；工具实现应尽量使用可配置的 provider、网络和文件读取超时，并在步骤边界检查取消/超时状态。

## GIS 环境启动需要显式设置 GDAL/PROJ 数据目录

### 现象

真实 GIS 链路可以完成，但启动日志出现 `GDAL_DATA is not defined`、找不到 `gdalvrt.xsd` 等警告。

### 根因

Conda 环境中的 GDAL/PROJ 数据文件位于环境自己的 `Library/share` 目录，直接通过包装命令启动服务时，相关环境变量不一定被正确设置。

### 诊断

在 GIS 环境执行一次真实矢量/栅格读取，检查 stderr 是否包含 GDAL_DATA、PROJ_LIB 或 gdalvrt.xsd 警告；不要把这些警告误判为统计结果错误。

### 修复

GIS 启动脚本设置 `GDAL_DATA` 和 `PROJ_LIB`，并使用 `conda run --no-capture-output` 启动服务，确保依赖数据目录和日志行为稳定。

### 预防

新增 GIS 启动方式时同时验证环境变量、真实 GeoJSON 读取、Rasterio 读取和服务日志；普通 Python memory 模式不应依赖这些变量。

## 多步骤失败不能丢失已完成结果

### 现象

多步骤任务中某一步失败后，整个 Run 变成 FAILED，但用户无法区分之前哪些步骤已经成功、哪些步骤根本没有执行。

### 根因

Runtime 的 fail-fast 异常路径只设置了 Run 级错误，没有为后续 StepRun 写入阻塞状态；前端也只认识 COMPLETED/FAILED 等常见状态。

### 诊断

构造一个第二步失败的三步计划，检查已完成步骤是否保留 result、失败步骤是否有 error、后续步骤是否仍停留在 PENDING。

### 修复

明确采用 fail-fast 契约：失败步骤为 FAILED，所有后续未执行步骤为 BLOCKED 并记录 `blocked by failed step` 原因；前端增加“已阻塞”状态。

### 预防

多步骤工具测试必须覆盖成功、失败、阻塞三类 StepRun 状态，并确保 trace/API 不把 BLOCKED 误报为已执行。

## 真实坡度和土地利用分析不能继续使用占位结果

### 现象

如果 DEM、土地利用只返回元数据或通用数值统计，用户无法回答“一个行政区的地形和土地利用分布如何”，前端也无法区分坡度与类别组成。

### 根因

坡度不是独立的现成字段，需要从 DEM 像元和像元尺寸动态推导；土地利用是分类栅格，均值、最小值和最大值不能表达类别占比。向量行政区与栅格之间还必须进行 CRS 转换，并处理无交集区域。

### 修复

新增 `get_zonal_slope_statistics`，使用 Rasterio 分块/裁剪后的 DEM 像元，根据像元尺寸用梯度推导坡度（度）；新增 `get_zonal_land_use_distribution`，返回受控的类别编码、像元数和占比。规则规划器可为高程、坡度、土地利用请求生成多工具计划，Console 展示均值和类别占比。

### 预防

不要把坡度 fallback 或类别编码语义伪装成真实分析结果。新增栅格业务工具时，应同时验证真实像元数、CRS 转换、无交集错误、答案组合、前端摘要和 GIS 环境回归。

## 同一 Conda 环境的 Python 进程仍可能缺少 GDAL 数据目录

### 现象

直接调用 `spatial-agent-gis` 环境中的 `python.exe` 时，Rasterio 可以部分读取栅格，但日志出现 `GDAL_DATA is not defined`、找不到 `gdalvrt.xsd` 或 `header.dxf`，复杂重投影调用还可能异常退出。

### 根因

解释器路径相同不等于启动进程继承了完整的 Conda shell 状态。GDAL/PROJ 的数据目录和动态库目录需要通过环境变量和 PATH 显式提供；`conda run`、直接路径调用和用户 PowerShell 会话也不一定共享变量。

### 修复

`scripts/start_console.ps1 -Mode gis` 现在自动定位 GIS Python，校验 `Library/share/gdal` 和 `Library/share/proj`，设置 `GDAL_DATA`、`PROJ_LIB`、PATH，并直接使用该环境解释器启动服务，不要求用户手动 `conda activate`。

### 预防

GIS 服务统一通过项目启动脚本启动，不要让用户手工拼接 Python 路径或依赖沙箱与用户 PowerShell 同步环境变量。

## Demo 启动方式不能直接作为生产部署方式

### 现象

开发入口使用本机绝对路径、标准库 HTTP Server 和当前 Shell 状态，换机器或由进程管理器启动时容易丢失 GIS 依赖、数据挂载和密钥配置。

### 修复

增加 `production_api.py`、`requirements-prod.txt`、`Dockerfile` 和 `docker-compose.prod.yml`。生产入口使用 Uvicorn，容器固定 Rasterio/GDAL/PROJ，数据只读挂载，结果单独挂载，模型配置通过 `.env.production` 注入，并提供 liveness/readiness 两级健康检查。

### 预防

开发脚本只用于本地演示；生产部署必须固定依赖、显式注入环境变量、隔离密钥和数据，并让 readiness 在 GIS 能力不可用时返回失败。

## Docker Desktop 的 WSL 安装源与 Docker 镜像源是两条链路

### 现象

Docker Desktop 安装完成后，可能因为 WSL 未安装而无法启动 Linux 引擎。即使配置了 Docker 国内镜像，也不能解决 WSL 组件缺失。

### 修复

先启用 `Microsoft-Windows-Subsystem-Linux` 和 `VirtualMachinePlatform`，再通过国内 GitHub 加速地址安装新版 WSL MSI，并设置默认 WSL 版本为 2。Docker 镜像拉取则单独使用 DaoCloud 代理；项目容器的 Conda GIS 依赖使用清华 Conda 镜像。

### 预防

部署检查必须分别验证 WSL/Docker 引擎可用性和 Docker registry/Conda 下载链路，不要把 Docker Hub 镜像源当成 WSL 安装源。

## Docker BuildKit 构建无输出并长时间卡住

### 现象

生产镜像执行 `docker compose build` 或 `docker build` 时，命令保持运行但没有构建日志，镜像标签和创建时间也没有变化。即使使用国内基础镜像和 Conda/PyPI 镜像，现象仍可能出现。

### 根因

构建过程由 Docker Desktop 的 BuildKit 后端执行，命令行前端可能在基础镜像解析、Conda 元数据下载或构建缓存通信阶段等待；仅看到 Docker CLI 进程存在，不能说明镜像已经构建完成。

### 诊断

同时检查 BuildKit/Buildx 子进程、镜像的创建时间和 Docker build cache。不要在没有新镜像 ID 的情况下启动生产容器并宣称安全修复已生效。Compose 和原生 `docker build` 都复现时，问题位于 Docker Desktop/BuildKit 或其网络链路，而不是 Compose 文件本身。

### 修复

停止明确的遗留构建进程，保留已有镜像和数据；确认 `.dockerignore` 已提交后再重试构建。构建成功的判据是命令正常退出且镜像 ID/创建时间更新，随后再启动 Compose 并检查 `/health/ready`。

### 预防

生产镜像构建应设置明确超时并保存构建日志；部署验证必须区分“代码已推送”“镜像已生成”和“容器已就绪”三个状态。不要使用包含本地私有配置的旧镜像替代新镜像。

## Compose env_file 不参与宿主机卷路径插值

### 现象

`.env.production` 中已经设置了本地 GIS 数据目录，但容器仍然挂载项目下的空 `./data`，健康检查显示目录存在，真实工具调用却返回 `dataset has no files`。

### 根因

Compose 的 `env_file` 只负责向容器注入环境变量，不负责解析 Compose 文件中的 `${VAR}` 宿主机卷路径。卷路径插值发生在 Compose 启动命令解析阶段。

### 修复

使用 `docker compose --env-file .env.production -f docker-compose.prod.yml up ...`，让同一配置文件参与宿主机路径插值；生产数据仍以只读 bind mount 提供，不复制进镜像。

### 预防

部署文档必须明确区分“容器环境变量”和“Compose 宿主机插值变量”，并用真实 GIS 请求验证挂载内容，而不能只检查目录是否存在。

## Linux GIS 容器不能复用 Windows Conda 的 GDAL 路径

### 现象

容器中的 Rasterio 元数据查询可以工作，但行政区 GeoPandas 查询或区域栅格分析失败，并提示 GDAL data directory 不包含正确的 GDAL 数据文件。

### 根因

Windows Conda 环境常使用 `Library/share/gdal` 和 `Library/share/proj`；Linux micromamba 环境的实际目录是 `share/gdal` 和 `share/proj`。直接复制 Windows 启动配置到 Linux 容器会让 GDAL 指向不存在或错误的目录。

### 修复

容器 Dockerfile 使用 `/opt/conda/envs/spatial-agent-gis/share/gdal` 和 `/opt/conda/envs/spatial-agent-gis/share/proj`，并通过真实 GeoPandas 行政区查询和区域栅格统计验证，而不只检查 Python 包是否可导入。

### 预防

不同操作系统和环境类型必须分别确认 GDAL/PROJ 数据目录；生产 readiness 还应增加一次轻量真实矢量读取检查，避免只报告依赖存在而遗漏运行时路径错误。
# 混合 CRS 的 GeoJSON 直接合并会导致空间预览失真

## 现象

建设适宜性分析接口执行成功并导出了候选 Polygon，但 Console 的空间预览没有正确显示候选区域。

## 根因

一次运行可能同时导出行政区边界和栅格候选面。行政区边界使用经纬度 CRS（例如 EPSG:4490），候选面使用栅格 CRS（例如 EPSG:32649）。原实现把两类坐标直接合并计算 SVG 范围，且没有保留每个要素的 CRS；异步 GeoJSON 加载失败也没有反馈。

## 修复

导出服务把几何来源和 CRS 写入每个 Feature 的 properties。Console 对建设候选优先显示对应栅格图层，并按 CRS 分组后计算范围；GeoJSON 请求失败或坐标无效时显示中文空态。

## 预防

合并不同空间来源的 GeoJSON 前必须保留 CRS 和来源信息，预览层不能假设所有 Feature 使用同一坐标系。空间预览回归测试应覆盖 Polygon、MultiPolygon、混合 CRS、无几何和资源请求失败。
