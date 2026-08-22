# Agent 开发问题记录

## 超大空间范围请求不能直接作为单次下载

### 现象

对武汉市约 `1.38° x 1.39°` 的外包络直接调用 OSM `map` API，甚至洪山区约 `0.02° x 0.02°` 的小样本请求，在当前网络环境中也可能连接超时；而同区域的 Overpass 小网格查询可以返回结果。

### 根因

OSM API 的 bbox 读取接口面向对象编辑和小范围读取，不适合整市级主题数据导出。道路、水体对象数量随范围快速增长，服务端响应体、查询耗时和客户端内存都会成为限制。外包络还会包含行政区边界之外的周边对象。

### 修复

整市数据采用分块下载：使用严格行政区边界计算外包络，切成固定网格，逐格查询并记录 bbox、时间和失败状态；本地按 OSM element 的 `type+id` 去重，再转换为 GeoPackage/GeoJSON 并按行政区裁切。对大范围数据优先寻找合法区域 PBF 导出，避免下载整个中国数据。

### 预防

空间数据接入测试必须先做小网格容量探测，再决定网格大小和并发度。下载器需要支持超时重试、断点续传、响应大小上限、临时文件隔离和 ODbL attribution；不能把一次请求成功误认为全市数据链路可用，也不能把外包络结果直接标注为武汉市结果。

## 浮点累加会生成零宽度空间网格

### 现象

将 `0.1°` 网格进一步拆成 `0.05°` 网格时，浮点数逐次累加可能让最后一个网格的 west 和 east 相等，下载器因此发出无效 bbox 请求并产生超时。

### 根因

网格边界使用 `x += tile_size` 和 `while x < east` 计算，二进制浮点误差会让循环边界与理论边界不一致。空间切片不能依赖连续浮点累加的精确相等判断。

### 修复

先使用 `ceil(extent / tile_size)` 计算行列数量，再用整数行列号计算每个网格起止边界，并在发起请求前校验 west < east、south < north。

### 预防

网格生成测试必须覆盖不能整除的范围、浮点小数边界和子网格拆分场景；任何下载请求前都应拒绝零面积 bbox。

## GIS 环境通过 Conda 启动时中文输出可能触发 GBK 编码错误

### 现象

GIS 转换脚本本身已经写出 GeoPackage，但通过 `conda run -n spatial-agent-gis` 转发包含中文或 OSM attribution 的 JSON 时，Conda 外层输出报 `UnicodeEncodeError: 'gbk' codec can't encode character`，命令被误判为失败。

### 根因

Windows PowerShell/Conda 外层输出编码与 Python 脚本的 UTF-8 JSON 输出不一致。这个错误发生在 Conda 捕获并转发 stdout 的阶段，不代表 GDAL 或 GeoPackage 写入失败。

### 修复

GIS 任务使用环境内 Python 可执行文件直接启动，并设置 `PYTHONIOENCODING=utf-8`；同时显式设置 `GDAL_DATA` 和 `PROJ_LIB`，确保 GDAL/PROJ 能找到运行时数据目录。转换脚本的测试保持为 GIS 环境专用，默认 Python 环境只加载纯标准库部分或跳过 GIS 测试。

### 预防

生产脚本不应依赖终端默认编码；所有机器可读输出使用 UTF-8。GIS 启动脚本应集中设置 Python、GDAL_DATA、PROJ_LIB 和日志编码，并分别验证“数据文件已写出”和“命令 stdout 成功”两个结果。

## 新增空间连接结果引用后必须提供可导出缓存

### 现象

GeoPackage 的 `spatial_join` 已经计算出道路-水体邻近关系并返回 `gpkg://join/...`，但服务开启 `export_geojson=true` 时，导出器无法根据该引用找到几何结果。

### 根因

工具结果引用是执行结果与地图导出之间的契约。新增工具只返回聚合计数而没有把受限的连接结果放入 backend 缓存，导致工具执行成功和结果导出使用了两套不完整的生命周期。

### 修复

空间连接在 backend 中缓存最多 10,000 条连接结果，并让 `export_result` 统一处理 `gpkg://join/...` 引用；服务仍只导出受限 GeoJSON，不把全量连接结果放入模型上下文。

### 预防

新增任何返回 `result_ref` 的工具时，必须同时验证：直接调用成功、服务启用 GeoJSON 导出成功、导出的几何 CRS 和来源正确、超过上限时仍能稳定截断。不能只测试 count 或 COMPLETED 状态。

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

## 后续增强

仅在前端按 CRS 分组仍然无法同时叠加行政区边界和候选栅格面。导出阶段现统一转换到 `EPSG:4326` 作为展示坐标系，并在 Feature 属性中保留 `geometry_source_crs`，从而兼顾叠加显示与数据溯源。

# 前端地图库不能成为唯一的空间预览依赖

## 现象

引入 Leaflet 后，如果浏览器或内网无法访问公共 CDN，交互地图可能无法初始化。

## 修复

Leaflet 只负责增强交互，不依赖在线底图；初始化失败时自动回退到项目原有 SVG 预览。这样外部 CDN 不可用时，候选区域和行政区边界仍然可见。

## 预防

前端新增公开三方库时必须保留无库降级路径，并把“库资源可用”和“空间数据可渲染”分开诊断，不能因为 CDN 失败而丢失核心分析结果。

地图交互回归使用浏览器烟测断言 Leaflet 或 SVG 至少生成一个矢量路径，不能只断言页面 HTTP 200 或地图容器存在。

## Leaflet 内部 SVG 不能使用全局地图 SVG 尺寸样式

Leaflet 的矢量图层自身也会生成 `<svg>`。如果页面使用 `.map svg { width:100%; height:260px }`，会覆盖 Leaflet 对 overlay SVG 的尺寸和定位，表现为地图容器有背景但看不到图形。降级 SVG 应改为 `.map > svg`，并单独恢复 `.leaflet-overlay-pane svg` 的 Leaflet 尺寸规则。

## 会话上下文需要显式隔离

同一 `session_id` 的后续请求可以基于上一轮请求继续分析，例如“继续分析这个结果”。当前 Demo 用受控的中文追问关键词拼接上一轮请求，新会话不会继承上下文。后续若需要引用具体结果，应升级为结构化 `result_ref`，不要把自然语言拼接当作长期上下文协议。

## 阈值对比应限制规模并复用受控工具链

多阈值对比不能让模型自由生成任意数量的任务。当前接口限制最多 6 个阈值、每个阈值限制在 1 到 45 度，并复用既有建设适宜性工具和 GIS 后端，返回受控摘要而不是重复导出所有几何。

## 在线底图必须是可选增强

OpenStreetMap 底图依赖浏览器出站网络，不应成为候选区域渲染的前置条件。默认使用纯矢量图层，在线底图通过 Leaflet 图层控制可选；网络失败时保留分析图层和 SVG 降级路径。

## 开放式对话不能绕过工具执行边界

空间问题不应依赖固定问题白名单，但也不能让模型直接编造 GIS 结果。Planner 现在使用结构化决策：空间问题必须生成注册工具步骤，通用问题可以返回 `direct_answer`，未知或当前能力不足的问题返回澄清；Runtime 对直接回答允许零工具步骤，对空间计划仍执行完整 ToolRegistry 校验。

## 真实模型三类决策需要独立验收

### 现象

真实模型即使能够返回合法 JSON，也可能把通用问答、空间分析和暂不支持的空间问题混在同一条执行路径中，导致前端无法判断是否真的调用了 GIS 工具。

### 诊断

使用同一真实模型分别测试通用问题、已注册空间能力和未注册空间能力，并同时检查 Run 状态、工具步骤数量、工具名称和最终答案。只检查 HTTP 200 或 JSON 可解析是不够的。

### 修复

结构化决策固定为三类：通用问题返回 `direct_answer` 且零工具步骤；空间问题返回完整 TaskPlan 并由 ToolRegistry 执行；未知空间能力返回 `NEEDS_CLARIFICATION`。同时禁止 `direct_answer` 携带工具步骤，避免模型输出中的隐藏步骤被静默忽略。

### 预防

真实模型 smoke test 至少覆盖三类决策，并在真实 GIS 环境额外验证一个元数据任务、一个区域统计任务和一个空间筛选任务。测试应记录状态和步骤摘要，不记录 API key 或完整私有模型响应。

## 生产多进程会丢失内存会话状态

### 现象

生产容器开启多个 Uvicorn worker 后，同一个 `session_id` 的澄清追问可能偶尔仍返回 `NEEDS_CLARIFICATION`，而不是使用上一轮保存的上下文完成任务。

### 根因

`AgentService`、`InMemoryConversationStore` 和运行记录使用进程内存。多个 worker 不共享这些对象，请求被负载到不同进程时，后续请求看不到前一进程保存的 pending clarification。

### 修复

先用单 worker 保证旧版本 demo 的行为一致，随后新增 SQLite 状态存储，将会话澄清和运行快照写入共享文件，使多个 worker 可以读取同一状态。更大规模部署仍应迁移到 Redis、数据库或其他独立共享存储，不能仅增加 Uvicorn worker 数量。

### 预防

生产验收必须连续使用同一 `session_id` 完成“缺少行政区名称 -> 补充洪山区”的 API 流程，并在多 worker 配置下重复验证。部署文档要明确 SQLite 文件路径、备份方式和更大规模部署的共享数据库要求。

## SQLite 连接上下文不能只依赖事务管理

### 现象

SQLite 测试在 Windows 下完成后，临时数据库文件仍被占用，清理目录时报 `WinError 32`；长期运行还会积累未关闭连接警告。

### 根因

`with sqlite3.Connection` 只负责事务提交或回滚，不会自动关闭连接。把它当作完整的资源上下文会留下文件句柄。

### 修复

存储适配器使用显式连接上下文：进入时创建连接，事务结束后在 `finally` 中调用 `close()`；同时保留 WAL 和 busy timeout 以支持并发读写。

### 预防

SQLite 存储测试必须覆盖 Windows 文件清理、Service/Runtime 重建和多个 session 隔离，并检查测试输出不能出现未关闭连接警告。

## 运行快照、取消控制和历史索引不能各自使用不同存储

### 现象

运行快照已经持久化到 SQLite，但取消标记仍保存在 worker 内存中，`GET /runs` 和 `GET /metrics` 仍只扫描导出的 artifact。服务重启或请求落到不同 worker 后，取消和历史列表可能与真实运行状态不一致。

### 根因

运行控制、运行快照和历史查询分别由 Runtime 内存集合、SQLite 快照表和文件 artifact 实现，三个生命周期没有统一的持久化边界。

### 修复

SQLite 增加 `run_controls` 表和取消读写接口；Runtime 在步骤边界同时检查持久化取消标记；生产 SQLite 模式的 `/runs` 和 `/metrics` 直接读取运行快照，因此不依赖是否导出 artifact。

### 预防

跨 worker 验收必须覆盖取消请求、失败运行查询、重启后运行快照和未导出运行的指标。取消仍是协作式的，不能把数据库标记误认为可以强制终止第三方调用。

## 局部模块测试通过不代表产品流程完整

### 现象

Planner、GIS 后端、地图预览和 API 各自有测试，但缺少统一的核心用户流程验收时，所有局部测试都通过，仍可能不知道一次真实空间分析能否从提问完整走到结果展示。

### 根因

测试按技术模块和历史里程碑增长，没有同步维护用户流程、工具链、结果契约和前端展示之间的整体关系。

### 修复

新增核心流程用例和整体验收文档，集中覆盖 DEM 元数据、行政区区域分析、建设适宜性、澄清追问和不支持空间领域，并分别用内存规则路径和真实 GIS 路径验证。

### 预防

每个涉及 Planner、工具、空间后端或前端结果展示的改动，都必须先通过核心流程验收，再运行对应模块测试。新增能力应先说明它属于哪条用户流程，不能只增加孤立的工具测试。

## 自然语言前缀未清洗会造成空间结果为空

### 现象

“分析洪山区土地利用分布”可以命中真实像元，但“查看洪山区土地覆盖情况”虽然选择了同一个工具，结果却提示行政区不存在。

### 根因

行政区名称正则会把句首动词一起捕获。规划器只清洗了“查询、分析”等前缀，没有清洗“查看、帮我、请”，导致后端收到“查看洪山区”而不是“洪山区”。

### 修复

扩展受控前缀清洗列表，并在自然语言变体验收中同时检查工具选择和解析后的 `admin_name`，不只检查 Run 是否为 `COMPLETED`。

### 预防

真实 GIS 变体测试必须检查最终工具参数和实际统计像元，不能把业务错误包装成成功状态后就认为流程通过。

## 真实模型计划成功但结果总结可能退化为步骤计数

### 现象

真实模型可以正确选择 `get_zonal_land_use_distribution` 或 `get_zonal_buildability_analysis` 并成功执行，但最终答案只显示“已完成若干工具步骤”，没有返回类别占比、候选比例或结果引用。

### 根因

`AnswerComposer` 过度依赖 Planner 返回的 `output.type`，且只为规则规划器常用的输出类型实现了总结分支。真实模型生成的合法计划可能使用不同的输出类型或只包含一个专用工具。

### 修复

结果组合器改为同时依据已执行工具和输出类型识别结果，增加坡度、土地利用分布和建设候选的专用中文摘要。这样不同 Planner 只要通过相同工具契约，都能获得一致的事实结果。

### 预防

真实模型端到端验收必须同时检查工具选择、状态、实际统计字段和最终答案；“COMPLETED”与“工具执行成功”不能替代用户可读结果验收。

## 窄屏控制台中的长环境标识会造成横向溢出

### 现象

Console 在手机宽度下将“规划器”和“空间后端”保持双列时，右侧控件被截断；辅助说明中的 `spatial-agent-gis` 等长标识也可能撑破页面宽度。

### 根因

桌面布局的双列表单没有在窄屏切换为单列，且连续英文或命令标识默认不一定会在容器内断行。

### 修复

移动端媒体查询将侧栏双列控件改为单列，并对环境说明启用任意位置断词，保持页面不产生水平滚动。

### 预防

前端视觉改动必须至少检查桌面和手机宽度截图；包含命令、路径、模型名或环境名的文案要显式考虑断行策略。

## 分析控制台的对话区过大时会稀释结果信息密度

### 现象

对话区和分析结果使用同样的整行大面板时，页面首屏会被输入框和空白消息区占据，结果卡片需要滚动很久才能看到；用户也难以同时观察提问和分析结论。

### 根因

页面只按功能顺序纵向排列模块，没有根据桌面工作流区分“持续输入区”和“结果工作区”，对话面板高度也没有独立约束。

### 修复

桌面端改为左侧设置、中间分析结果、右侧窄对话窗的三栏布局；对话窗固定适中高度，消息区在窗内滚动，分析卡片使用更紧凑的间距和内边距。

### 预防

工作台类页面应优先验证首屏信息密度和关键结果可见性，不能只按组件数量堆叠全宽大卡片；桌面布局需要单独定义侧栏、工作区和持续交互区的尺寸契约。

## 固定显示所有结果面板会削弱 Agent 的动态输出契约

### 现象

即使用户只查询一个栅格元数据，页面也预先显示高程、建设适宜性、阈值对比、地图和血缘等大量空面板，结果类型越多，界面越臃肿。

### 根因

前端按“所有可能能力”设计静态面板，而不是把 Agent 的工具计划和工具结果作为结果组件选择依据。这样新增工具时还会继续堆叠面板，且初始状态无法表达“尚未决定结果类型”。

### 修复

结果工作区初始只显示空状态；运行后由已执行工具和结果引用动态显示通用结果组件及对应的栅格统计、综合分析、建设候选、地图和阈值对比组件。对话设置移入对话窗，并将示例问题折叠。

### 预防

新增 Agent 工具时应同时定义它对应的结果组件和显示条件。通用结果区只承载回答、计划、轨迹和指标，专用结果区必须由实际工具结果激活，不能因为能力存在就默认展示。

## 规则规划器把基础问候误判为空间澄清

### 现象

用户输入“你好”时，规则规划器返回 `NEEDS_CLARIFICATION`，前端只显示“需要补充信息”，没有给出正常的对话回应。

### 根因

开放式对话边界虽然已经支持能力介绍和真实模型的 `direct_answer`，但规则规划器只有空间请求分支和少量帮助关键词，没有覆盖基础问候语。

### 修复

增加受控的中英文基础问候匹配，直接生成零工具步骤的 `direct_answer`，并增加核心流程回归测试。未知空间问题仍然进入澄清，不放宽工具执行边界。

### 预防

开放式对话验收至少覆盖问候、能力介绍、已支持空间问题和未支持空间问题四类，分别检查回答、工具步骤和运行状态，不能只验证空间工具链。

## 会话下拉切换只清空前端视图而没有恢复历史

### 现象

切换“对话1”和“对话2”时，前端虽然改变了选择项，但只显示新的欢迎语；刷新或切换后看不到该会话之前的消息和最近一次空间结果。

### 根因

SQLite 已经分别保存会话状态和运行快照，但运行快照没有记录 `session_id`，也没有按会话查询运行历史的 API。前端只能读取全局运行列表，无法可靠恢复某个会话。

### 修复

将 `session_id` 纳入 `AgentRunResult` 和 SQLite 快照，增加 `GET /sessions/{session_id}/runs`。前端切换会话时恢复消息摘要，并通过最近一次 `run_id` 加载完整结果，使结果组件继续由原始 `result_type` 动态决定。

### 预防

会话功能验收必须覆盖创建两个会话、分别运行任务、切换会话、刷新页面和恢复最近结果；不能只断言下拉选项存在或会话编号正确。

## 浏览器烟测在会话列表加载前设置下拉值会落到默认会话

### 现象

浏览器自动化脚本创建新会话后立即设置 `<select>` 的值，脚本表面上执行成功，但历史消息没有出现在目标会话中，运行可能被发送到默认会话。

### 根因

控制台初始化会异步调用 `loadSessions()`。如果测试在选项尚未插入 DOM 前设置不存在的 value，浏览器不会选择该会话；后续请求使用的仍是默认值或空值。

### 修复

浏览器烟测在每次选择会话前显式等待 `loadSessions()` 完成，再设置 value 和调用 `restoreSession()`，同时断言用户消息和助手消息都已恢复。

### 预防

前端 E2E 测试必须等待数据驱动的控件完成初始化，不能用固定 sleep 替代选项存在性和选中值断言。

## 地图烟测未设置 GIS 后端且没有等待异步对话完成

### 现象

建设适宜性地图烟测找不到任何 SVG 或 Leaflet 矢量路径，控制台状态仍显示“待机”。

### 根因

测试脚本沿用了默认“内存演示”后端，而页面会拒绝需要真实栅格的分析请求；同时脚本触发 `sendChat()` 后没有等待 Promise 完成，固定等待结束时可能尚未进入地图加载。

### 修复

烟测在调用前显式选择“本地 GIS”，并通过 CDP 的 `awaitPromise` 等待 `sendChat()` 完成后，再等待 GeoJSON 图层加载。

### 预防

浏览器空间测试应把 Planner、后端和所需数据视为前置条件，同时等待实际异步操作结束；不能仅依据页面初始默认值和经验性延时判断地图是否渲染。

## GeoJSON artifact 引用不等于存在可绘制几何

### 现象

一次运行返回了 `geojson_ref`，但内存演示后端没有真实几何；如果前端只依据引用存在来显示地图，会出现空地图或误报空间结果可用。

### 根因

artifact 是结果文件的传输引用，可能只包含步骤摘要或 `geometry: null`。引用存在只能说明文件可下载，不能说明其中存在可渲染空间要素。

### 修复

统一结果协议将 `references` 与 `geometry.available` 分开表达。只有执行结果携带真实几何来源，或展示 artifact 明确包含几何时，才将空间几何标记为可用。

### 预防

地图组件必须同时检查引用、几何数量和坐标有效性；内存后端、真实 GIS 后端和 GeoJSON 截断结果要分别验收。

## 地图选区不能只靠自然语言拼接传递

### 现象

用户在地图上点击区域后，如果只把区域名称拼接到输入框，下一轮分析可能丢失来源、CRS 和几何可用性，模型也无法区分用户明确选择的范围与普通文本提及。

### 根因

空间交互上下文和自然语言请求属于不同信息层。将几何上下文压缩成文本会丢失结构，也无法限制客户端传入的任意几何数据。

### 修复

增加受控 `spatial_context` 请求字段，只接受区域名、来源、CRS、几何类型和布尔可用性；服务端校验并截断字段，Planner 通过区域名绑定现有 GIS 工具链，前端地图点击后保留该上下文。

### 预防

地图交互测试必须检查选区上下文是否随下一次请求发送、是否仍经过 Planner 和 ToolRegistry，以及无名称或无效上下文不会绕过空间安全边界。

## 清空对话没有同步清空工作区

### 现象

点击“清空对话”后，消息列表虽然恢复为空，但左侧任务步骤、执行轨迹、分析结论、地图选区和中部结果仍然保留上一次运行的内容。

### 根因

前端将“清空消息”和“重置工作区”拆成了两个函数，但 `clearChat()` 只操作了 `messages` 容器，没有调用已经负责清理完整运行状态的 `resetConversationView()`。

### 修复

“清空对话”统一调用 `resetConversationView()`，再显示欢迎消息。该重置同时清理地图、选区上下文、结果面板、任务步骤、血缘和执行轨迹；阈值对比也复用当前地图选区的受控 `spatial_context`，不再从页面副标题猜行政区名称。

### 预防

前端清空、切换会话和新建会话必须共用完整状态重置函数，并增加静态或浏览器回归测试，至少验证结果区为空且地图选区已解除。

## 浏览器验收连接到旧服务会掩盖当前前端改动

### 现象

当前代码已经修改 `clearChat()`，但浏览器烟测仍观察到旧行为；切换到当前代码启动的服务后，地图烟测又因服务没有 GIS 能力而无法生成空间要素。

### 根因

本机 `8088` 端口同时被 Docker 相关服务占用，返回的页面不是当前工作区代码；而依赖本地 Python 默认环境启动的 `serve_api.py` 只具备内存后端，不能满足本地 GIS 地图烟测的前置条件。

### 修复

浏览器烟测支持 `CONSOLE_URL` 覆盖地址，并在当前代码服务上单独验证前端清空状态；地图烟测继续显式要求本地 GIS 后端和真实几何。验收前必须检查页面源码来源、端口和 `/health` 能力，不能只依据端口号。

### 预防

生产容器、GIS 控制台和普通内存服务使用不同端口；浏览器验收脚本应固定目标 URL，并先断言 `health.capabilities` 与测试场景匹配。

## 前端清空视图没有清理持久化会话历史

### 现象

点击“清空对话”后当前页面短暂变为空，但刷新页面或重新切换会话时，旧消息、左侧历史任务和上一次结果又被恢复。

### 根因

原有清空操作只重置浏览器 DOM；SQLite 中的运行快照、澄清状态和上一次请求仍然存在，会话恢复逻辑会按设计重新加载这些数据。

### 修复

增加 `POST /sessions/{session_id}/clear`，清除该会话的运行快照、取消控制、澄清状态和连续追问状态但保留会话编号；增加 `DELETE /sessions/{session_id}` 用于彻底删除会话。前端将“清空对话”和“删除对话”分成两个明确操作，并在清空后刷新历史任务列表及左侧工作区。

### 预防

涉及会话的 UI 操作必须同时验证内存视图、持久化快照和刷新后的恢复结果；“清空”与“删除”不能只靠按钮文案区分而没有独立 API 契约。

## 异步清空操作未等待服务端结果会读到旧界面

### 现象

清空操作已经改为调用服务端 API，但浏览器验收在点击按钮后立即读取 DOM，仍然看到旧结论和旧步骤。

### 根因

按钮事件触发了异步 `fetch`，而验收脚本没有等待 `clearChat()` 返回；读取时服务端请求和界面重置尚未完成。

### 修复

清空函数保持 Promise 返回值，浏览器烟测通过 `awaitPromise` 等待完整清空链路后再断言消息、结果和地图选区。

### 预防

所有涉及服务端请求的前端验收必须等待对应 Promise，不使用固定延时代替完成条件；生产代码应让异步动作可被测试调用和等待。

## 同步运行接口无法安全提供前端取消按钮

### 现象

前端希望在空间分析执行期间提供“取消”按钮，但当前 `POST /runs` 会一直等待 Agent 运行结束，响应返回前浏览器拿不到 `run_id`。

### 根因

取消 API 需要已有运行 ID，而同步 HTTP 请求把“创建运行”和“等待运行完成”合并成了一次调用；浏览器中止请求也不会可靠地停止服务端线程或第三方 GIS 调用。

### 修复

本阶段不增加表面上的假取消按钮，保留已经验证的 Runtime/API 协作式取消能力，并先实现不依赖异步作业队列的多区域对比。真正的前端取消将放到异步运行、状态轮询和运行 ID 先返回的架构阶段。

### 预防

设计前端运行控制时必须先确认运行生命周期契约：创建任务、获取 `run_id`、轮询状态、取消请求和最终结果不能被一个同步请求隐藏。

## 异步运行接入不能破坏原有结果渲染契约

### 现象

将同步分析改为异步提交后，如果前端直接改写 `sendChat()` 的结果处理，容易丢失原有结果面板、轨迹、GeoJSON 和错误展示。

### 根因

同步接口一次返回完整运行结果，异步接口先返回排队状态；两者响应时序不同，但前端已有渲染逻辑依赖统一的最终 payload。

### 修复

新增 `/runs/async` 和状态轮询，前端只在请求层适配异步过程，轮询到终态后仍返回原有结果结构给 `sendChat()`，并让取消按钮使用同一个 `run_id`。

### 预防

异步改造优先保持最终结果契约稳定；测试必须覆盖排队、执行中、完成、取消和失败状态，不能只断言异步接口返回了一个 ID。

## 异步运行必须保留同步结果契约

### 现象

异步任务先返回 `QUEUED`，如果前端直接把排队响应当作最终结果，会显示“已完成”但没有工具步骤、结论和证据。

### 根因

异步接口的提交响应和运行结果是两个生命周期阶段；原有结果组合器只接收完整的 `AgentRunResult`。

### 修复

服务端让后台运行继续写入原有状态快照，前端轮询 `GET /runs/{run_id}`，仅在终态把完整 payload 交给原有 `renderRun()`；取消也经过同一个运行 ID 和 Runtime 控制边界。

### 预防

异步验收必须检查 `QUEUED`、中间状态和终态之间的状态转换，并验证终态仍包含工具步骤、结果契约、轨迹和错误信息。

## Rasterio `from_bounds` 在当前 Windows GIS 环境触发原生崩溃

### 现象

真实执行“分析洪山区建设适宜性，坡度不超过 20 度，距离道路 500 米以内，避开水体”时，Python 进程直接退出，退出码为 `-1066598273`，没有 Python 异常或可捕获的 `ToolError`。

### 根因

土地利用栅格裁剪和 `transform_bounds` 均可正常完成。进一步的最小探针显示，即使只对固定的 `Affine` 变换调用 `rasterio.windows.from_bounds`，其内部 `rowcol` 路径也会在当前 Rasterio/GDAL/Python 组合中触发原生退出。问题不是 DEM 文件元数据损坏，也不是 `numpy.gradient` 或 `reproject` 本身造成的。

### 修复

栅格后端新增 `_safe_window_from_bounds`，对当前使用的北向上栅格使用纯 Python 仿射计算生成 window，并校验 bounds、旋转参数、宽高及边界后再交给 Rasterio 读取。真实 GIS 联合工作流回归已验证通过。

### 预防

遇到没有 Python traceback 的 GIS 进程退出，必须使用独立子进程和阶段标记定位到具体 Rasterio 调用；不能只测试“文件可以打开”。涉及 window 的代码应避免未经验证的 GDAL transformer 路径，并用真实数据回归锁定 native 崩溃。

## 对全量道路和水体做 `unary_union` 导致约束分析内存暴涨

### 现象

修复栅格崩溃后，联合约束进入道路/水体处理阶段时，进程内存增长到约 5 GB，测试在超时前无法完成。

### 根因

GeoPackage 中有约 68,903 条道路和 20,923 条水体。旧实现将全部道路合并后再整体缓冲、将全部水体合并后再相交，构建了非常大的临时几何；同时候选结果的 CRS 被硬编码为 `EPSG:4326`，没有使用栅格候选实际携带的 `EPSG:32650`。

### 修复

约束逻辑现在读取结果中的 CRS，选择米制投影，并使用道路/水体空间索引对每个候选几何查询局部要素，再做精确距离和相交判断。结果继续明确标记为有限候选样本约束，不宣称全像元精确适宜性。

### 预防

真实矢量规模回归必须同时观察耗时和内存，不能只断言结果数量。禁止对未经聚合规模评估的全量道路、水体直接 `unary_union` 或 buffer；跨后端传递几何时必须保留并消费 CRS。

## 多 UTM 分区栅格不能被误报为完全可用

### 现象

武汉 DEM 和土地利用文件都可以正常打开，但全量数据健康检查将它们标记为 `degraded`；逐文件结果显示文件分别使用 `EPSG:32649` 和 `EPSG:32650`。

### 根因

武汉数据跨越 UTM 分区。文件可读并不等于 CRS 已统一，若在拼接、window 读取或像元对齐时忽略这个差异，可能得到错误的空间关系或再次触发底层库问题。

### 修复

健康报告把“多个 CRS”作为明确的 warning，而不是伪装成 `ready`；实际区域分析继续在每个源栅格的 CRS 中做 bounds 转换，再将 DEM 重投影到土地利用网格。

### 预防

数据接入验收必须同时检查文件可读性和 CRS 一致性。多分区数据应在每次跨文件计算前做显式 CRS 转换/对齐，并在结果中保留 CRS 与覆盖范围证据。

## Docker CLI 能力存在但 Docker Engine 管道无权限

### 现象

生产验收尝试执行 `docker version` 或 `docker compose config` 时，Docker CLI 返回 `permission denied`，无法连接 `npipe:////./pipe/docker_engine`；这与 Dockerfile 或 Compose 配置语法错误不同。

### 根因

Windows 当前用户进程没有访问 Docker Desktop Engine named pipe 的权限，或 Docker Desktop/WSL2 引擎尚未对当前会话可用。CLI 文件存在不能证明 Engine 已启动且可调用。

### 修复

本阶段不修改系统权限，也不伪造容器验收结果；增加 `scripts/production_acceptance.ps1`，在 Engine 恢复后执行 liveness、readiness、异步提交、轮询和终态结果检查。与此同时用 SQLite 临时数据库完成服务重建后的异步运行快照验收。

### 预防

生产部署验收必须分别记录 Compose 配置解析、Engine 连接、容器健康、HTTP readiness 和业务异步结果；任一层不可访问时应标记为环境阻塞，而不是归因到应用代码或直接宣称部署成功。

## 生产验收固定 session 污染 SQLite 待澄清状态

### 现象

生产验收脚本第一次运行失败后，第二次即使发送“你好”，仍可能得到旧空间约束错误。容器健康、API 请求和当前 Planner 都正常，但验收脚本无法稳定复现独立场景。

### 根因

SQLite 会持久化 session 的待澄清请求。脚本固定使用同一个 `production-acceptance` session；上一次失败留下的上下文会被下一次请求自动合并，导致验收输入不再是脚本显示的原始请求。

### 修复

脚本每次运行生成唯一的 `production-acceptance-{guid}` session_id，避免复用历史上下文；实际产品仍保留固定 session 的多轮澄清语义。

### 预防

自动化验收必须为每次场景使用隔离 session，或在场景开始显式清空并验证持久化状态。不能仅凭请求文本判断测试输入没有被历史上下文改变。

## Windows PowerShell 未显式 UTF-8 导致中文验收请求变成问号

### 现象

生产 API 本身可以正确处理中文请求，但 `production_acceptance.ps1` 发送“你好”后，SQLite 运行快照中记录为 \"???\"，规则 Planner 返回缺少空间条件的澄清错误。

### 根因

Windows PowerShell 通过 `Invoke-RestMethod -Body` 发送字符串时，未声明 UTF-8 字节编码；请求头只有通用 `application/json`，服务端收到的中文已在客户端编码阶段丢失。

### 修复

验收脚本避免直接包含中文字面量，使用 Unicode code point 构造文本，再将 JSON 显式转换为 `[System.Text.Encoding]::UTF8.GetBytes(...)`，并发送 `application/json; charset=utf-8`。

### 预防

中文 API 的 PowerShell 验收必须检查服务端保存的原始 request 或最终 resolved_request；不能只依据 HTTP 200 判断编码正确。无 BOM UTF-8 脚本在 Windows PowerShell 5.1 中不应直接依赖中文源代码字面量，跨平台脚本应统一使用 UTF-8 bytes 或明确设置 charset。

## 轻量 HTTP 服务缺少 `GET /runs/{run_id}` 会让 Console 永久停在规划中

### 现象

`POST /runs/async` 可以返回 `QUEUED`，但 Console 轮询运行状态时一直显示“规划中”，专用结果面板不会出现。直接调用 AgentService 或同步 `POST /runs` 则正常。

### 根因

AgentService 已实现 `get_run`，生产 FastAPI 路由也有运行查询能力，但依赖标准库的 `serve_api.py` 只实现了 `GET /runs` 列表，没有实现单个运行详情路由。前端收到 404 后继续保留初始状态。

### 修复

轻量服务增加 `GET /runs/{run_id}?planner=...&backend=...`，将查询参数传给 AgentService；不存在的运行返回 404。新增 HTTP 契约测试，并通过当前代码启动的 Console 浏览器烟测验证异步健康检查面板可以显示。

### 预防

异步接口验收必须覆盖“提交、轮询、终态结果”三步，不能只断言提交接口返回了 `run_id`。同步和异步接口都应共享同一最终运行结果契约，服务实现之间也要对齐路由集合。

## 新增 preflight 后固定步骤下标导致验收漂移

### 现象

数据健康预检接入区域栅格统计后，真实 GIS 业务结果仍能完成，但测试读取 `steps[0]` 或 `steps[2]` 时拿到健康检查或错误步骤，出现断言失败、`KeyError`，容易误判为业务回归。

### 根因

执行步骤是带有依赖关系的可观察协议。新增前置工具会合法改变列表位置；测试和 provenance 验收却把步骤位置当成稳定接口，没有按工具 ID 或语义依赖查找。

### 修复

同步更新核心评测契约，并在受影响测试中断言新的 preflight 顺序；结果读取改为先确认工具 ID，再读取对应步骤。M55 的区域 DEM、土地利用和复合行政区栅格测试已覆盖健康步骤。

### 预防

验收应优先按 `tool`、`id` 和 `depends_on` 验证步骤语义，只有专门测试顺序时才使用固定下标。新增 preflight、审计、缓存等横切步骤后，必须同步更新 evaluation cases、provenance 测试和恢复文档。

## 数据健康状态只有标签而没有可执行能力

### 现象

健康检查可以显示数据集为 `ready`、`degraded` 或 `unavailable`，但 Planner/Runtime 仍可能继续调用依赖缺失数据的栅格工具，最终错误只出现在较晚的业务步骤，用户看不出为什么停止。

### 根因

数据状态和工具能力是两个不同维度：文件可读、CRS 有 warning，并不等价于每一种区域统计或联合筛选都可执行。旧协议只返回整体状态，没有声明数据集支持哪些操作，也没有在工具边界消费这份证据。

### 修复

健康报告为每个数据集增加 `usable_for`，整体报告增加 `capabilities`；真实配置会根据 DEM/土地利用覆盖关系声明建设候选能力，内存演示明确返回空能力但保留占位结果。Runtime 在健康预检后发现必需数据 `unavailable` 时，在下游工具 dispatch 前失败，并把数据集、可用能力和切换 GIS 的建议写入答案与轨迹。

### 预防

新增数据工具必须同时定义依赖数据集、所需能力和不可用策略。`degraded`、`unavailable` 与内存演示不能混用；健康报告应作为执行策略证据消费，而不是只作为前端装饰信息。

## 开发服务与生产服务路由不一致

### 现象

统一能力目录已接入标准库开发服务和本地测试，但重建生产容器后访问 `/capabilities` 返回 404；健康、异步运行和原有 Console 路由仍然正常。

### 根因

开发环境入口是 `serve_api.py`，生产容器入口是 `production_api.py`。新增 API 只修改了前者，测试也只覆盖了标准库 Handler，没有把两种服务实现视为同一个 HTTP 契约。

### 修复

在生产 FastAPI 入口补充同一 `/capabilities` 路由，并增加生产入口契约测试。Compose 重建后验证返回能力版本和 8 项能力，未完成数据健康预检的建设筛选保持 `unknown`。

### 预防

新增 HTTP 路由必须同步检查所有运行入口、生产容器实际 CMD 和对应契约测试；部署验收不能只检查健康接口，还要请求新增业务路由。标准库服务和生产 ASGI 服务应共享返回模型或至少共享契约测试。

## 空间引用存在但几何证据状态不明确

### 现象

运行结果包含 `geojson_ref` 时，客户端容易直接显示地图可用；但内存后端生成的 GeoJSON 可能只有步骤摘要和 `geometry: null`，真实 GIS 候选筛选则可能包含可绘制要素。

### 根因

传输引用、结果摘要和空间几何是不同层次的证据。旧 envelope 只有布尔 `geometry.available`，无法解释“没有几何”“边界几何”“真实候选几何”和“摘要截断”的差异。

### 修复

结果契约新增 `geometry.status`、`reason`、`feature_count` 和 `truncated`，支持 `real_geometry`、`boundary_geometry`、`no_geometry`、`truncated_geometry` 和 `unknown`。Console 显示空间证据状态；内存 API 验证为 `no_geometry`，真实 GIS 建设筛选验证为 `real_geometry` 且包含 101 个要素。

### 预防

地图组件必须同时检查引用、证据状态、要素数量和坐标有效性。评测和答案不能把工具成功、GeoJSON 可下载或模型规划成功当成真实空间几何已生成。

## 运行时能力快照不能替代业务能力验收

### 现象

`GET /capabilities/runtime` 可以返回当前数据集的质量、覆盖范围、CRS、文件数量和更新时间，但仅凭接口返回成功，容易把“能读取数据元信息”误认为“对应空间分析已经可执行”或“已经生成真实几何”。

### 根因

运行时能力快照是按请求生成的环境观测结果，描述数据和配置的当前状态；真实业务能力还取决于工具依赖、跨栅格覆盖、像元对齐、几何证据状态以及实际 dispatch 结果。静态能力目录、健康状态、工具成功和真实空间结果属于不同证据层级。

### 修复

M60 增加 `agent/runtime_capabilities.py` 和 `runtime_capability_catalog()`，在快照中保留数据质量、覆盖范围、CRS、文件数、检查文件数和 `updated_at`；HTTP 与生产验收脚本分别暴露并检查快照。业务结果仍由具体工具、结果 envelope 和几何证据字段确认。

### 预防

前端、评测和部署验收必须同时检查运行时健康状态、能力 ID、工具执行结果和 `geometry.status`。快照过期、数据为 `degraded` 或缺少跨数据集覆盖证据时，应显示限制并继续走能力门控，不能仅依据 HTTP 200 或目录中的 `ready` 标签宣告成功。

## 容器完整健康状态被可选数据缺失拉低

### 现象

生产容器的 `/capabilities/runtime` 可以确认行政区、DEM 和土地利用逐项为 `ready`，但整体 `health_status` 为 `unavailable`，原因是容器示例数据卷没有挂载道路和水体；生产验收如果只看整体状态，会误以为所有核心能力都不可用。

### 根因

健康报告当前按配置请求的全量数据集聚合状态。能力目录虽然已经保留逐能力的 `dataset_gate` 和逐数据集证据，但没有把核心数据、可选数据和依赖特定工作流的数据分层表达。

### 修复

M60 保留整体 `unavailable` 的诚实语义，同时在运行时快照中输出逐数据集 `data_evidence` 和逐能力 `runtime_evidence`；生产验收允许该降级状态并继续检查能力列表、更新时间和异步业务契约，避免伪造“完全健康”。

### 预防

后续生产配置应明确数据集的必需级别和能力依赖。健康接口需要同时提供整体状态、核心状态、可选数据状态和能力级门控；部署验收必须验证缺失可选数据不会错误阻断无关核心工作流，也不能把单个核心数据缺失降级成普通 warning。

## 并行子任务重复修改公共辅助函数

### 现象

多个并行子任务分别为异步服务增加了同名的 `_async_response`、`_async_status` 和 payload 辅助函数，后定义版本覆盖前定义版本；部分调用还使用了不存在的实例方法，导致重复提交或重启恢复在运行时才失败。

### 根因

并行任务虽然写入范围相近，但没有把公共辅助函数和返回字段作为集成所有权；各任务分别完成后直接叠加，缺少单一公共契约审查。

### 修复

集成时保留单一实现，统一 `idempotent`/`reused` 兼容字段，修复实例/模块调用边界，并用并发重复提交、显式运行 ID、重启接管和异常 worker 测试覆盖。

### 预防

并行任务必须声明公共符号所有权；同一模块只能有一个任务修改共享辅助函数。合并前运行重复定义扫描、静态编译和跨进程契约测试，不能只看各自专项测试通过。

## Goal 并发上限与工具状态不一致

### 现象

项目执行约定原先允许最多 5 个并行子任务，但当前 goal 工具只支持查询或标记 `complete`/`blocked`，不能直接修改已有 objective 文本。若只修改对话中的描述，后续恢复会话仍可能读取到旧的并发上限。

### 根因

goal 的生命周期状态和项目开发规则由不同机制维护，工具没有提供 objective 内容编辑接口；文档未明确声明当前有效规则时，历史里程碑中的并发记录容易被误认为仍然有效。

### 修复

将当前全局规则持久化到 `docs/agent-context-resume.md`、`docs/task-resume.md` 和 `docs/milestones.md`：最大并发度改为 4，任一阶段最多启动 4 个并行子任务。历史阶段保留其当时的事实记录；后续实际执行严格遵守 4 路上限。

### 预防

每次新阶段规划先读取恢复文档的当前全局执行规则，再启动并行任务；不要仅根据 goal 工具返回的 objective 文本判断最新并发限制。若工具接口无法更新 goal 文本，应在恢复文档中记录权威规则并在交接说明中指出该限制。

## Goal 并发上限再次调整

### 现象

M67 开始时项目文档将当前最大并发度记录为 4，但用户随后将 goal 的最大并发数调整为 3；此时已有 4 条子 agent 线程占用并发槽位。

### 根因

goal objective 不能由现有工具直接改写，且已完成的子 agent 仍会占用线程槽位，导致文档规则和实际可用并发资源可能短暂不一致。

### 修复

立即关闭一条仍在运行的 M67 Console 子任务，将当前有效规则同步改为最大并发度 3，并让后续阶段最多启动 3 个并行子任务。

### 预防

每次并发上限调整都要先回收超额子 agent，再修改恢复文档；启动新阶段前同时检查文档规则和实际线程槽位，不能只修改文字描述。

## 浏览器烟测固定等待和环境变量残留

### 现象

Chrome CDP 已连接且服务返回 200，但浏览器烟测偶发出现 `$ is not a function` 或一直无法找到 Console 控件。另一个 PowerShell 会话残留的 `CONSOLE_URL=http://127.0.0.1:8091/` 还可能让 Docker 8088 验收误访问已停止的本机 GIS 服务。

### 根因

烟测仅按固定毫秒数等待页面，没有等待内联 Console 脚本完成；同时 `const $` 是页面脚本的顶层词法绑定，不保证通过 `window.$` 可见。环境变量是进程级继承状态，脚本默认值不会覆盖已经存在的旧值。

### 修复

所有 Console CDP smoke 在导航后轮询 `typeof $` 和 `typeof sendChat`，就绪后才执行交互；脚本统一支持 `CDP_URL` 和 `CONSOLE_URL`，验收命令显式指定 8088 Docker 或 8091 GIS 目标。M66 已分别验证内存总览、Docker 健康、真实 GIS 地图和会话/清空流程。

### 预防

浏览器验收必须使用页面就绪条件而不是固定 sleep；切换服务入口时显式设置目标 URL，并在输出中记录后端、端口和数据环境。页面全局函数/变量的探测应按实际声明方式检查，不能默认要求 `window` 属性。

## 异步预写终态快照会阻断真实 worker

### 现象

异步提交为了让轮询立即读到 `PLANNING`，先把同一 `run_id` 写入状态库；worker 随后按同一 ID 调用同步运行入口，被幂等保护误判为已完成请求，实际规划没有执行。

### 根因

提交占位快照和运行结果快照复用了同一个幂等语义，但没有区分“内部 worker 正在执行”和“外部重复请求应复用”。

### 修复

异步提交只持久化作业记录，由 worker 使用受控 `_force_run_id` 边界写入真实运行快照；外部重复提交仍复用现有 `run_id`，并由 `get_run` 等待作业标记和结果快照达到一致终态。

### 预防

异步协议必须区分提交记录、运行快照和终态结果；测试至少覆盖首次提交、重复提交、同步重放、服务重启和 worker 异常，不能只断言拿到了 `run_id`。

## 新增空间澄清不能截断已有规则工作流

### 现象

为未支持空间问题增加意图澄清后，若把兜底分支放在旧道路/坡度参数校验之前，原本可执行的多步骤计划会提前变成 `NEEDS_CLARIFICATION`。

### 根因

Planner 的分支顺序本身是行为契约：能力识别兜底只能处理没有进入既有工作流的请求，不能抢先消费仍需参数校验或执行的请求。

### 修复

将空间意图兜底放在坡度阈值缺失校验之后，并增加旧 M1/M44 工作流回归与 M62 未知空间问题测试。

### 预防

扩展 Planner 时先绘制分支优先级：安全拒绝、通用回答、已支持完整计划、已支持但缺参数、开放式空间澄清。每个新兜底分支必须证明不会改变已有工具序列。

## 澄清信息只放在 error 文本会限制前端和 API

### 现象

开放式空间问题虽然可以返回中文澄清，但客户端只能解析一段文本，无法稳定知道匹配了哪些能力、缺少哪些参数，也无法生成下一步操作。

### 根因

澄清状态和用户可读消息被混在 `error` 字符串中；字符串适合兼容展示，不适合作为跨服务的结构化协议。

### 修复

`ClarificationNeeded` 增加可选详情，运行结果和 SQLite 快照保留 `clarification`，结果 envelope 和 Console 消费结构化字段，同时继续输出原有 `error`。

### 预防

新增需要前端决策的状态时，应同时定义结构化字段、兼容文本、持久化恢复和契约测试；不要让客户端通过正则解析错误消息来推断能力或缺失参数。

## 新结果类型可能被旧答案分支提前消费

### 现象

新增空间总览计划虽然返回了正确的 8 步工具序列和 `spatial_overview_result`，但最终答案仍被旧的地形/土地利用组合分支生成，导致道路和水体摘要没有出现在答案中。

### 根因

`AnswerComposer.compose` 先根据工具存在性判断通用组合结果，再判断计划声明的结果类型。多工具计划共享部分工具时，工具启发式分支会覆盖更具体的结果契约。

### 修复

对专用结果类型先做显式分派，再执行兼容性的工具启发式分派；为总览计划增加结果类型、工具序列和答案内容测试。

### 预防

新增多工具工作流时，结果类型是优先级更高的协议字段。答案组合器应先消费 `plan.output.type`，工具启发式只能作为旧计划的兼容兜底。

## 生产同步路由误传异步幂等参数

### 现象

生产容器健康检查、能力快照和异步接口均正常，但同步 `POST /runs` 返回 `AgentService.run() got an unexpected keyword argument 'idempotency_key'`。

### 根因

生产 FastAPI 路由复制异步提交字段时，把 `idempotency_key` 转发给同步 `AgentService.run`；服务层只在 `run_async` 实现该参数，标准开发服务没有暴露这个差异。

### 修复

从生产同步路由移除异步专用参数，并增加生产入口契约测试，使用假的同步服务捕获实际转发参数。

### 预防

同步、异步 API 的参数映射必须分别测试，不能仅验证路由存在或健康接口正常；生产容器验收至少要执行一次真实同步业务请求。

## GeoJSON 截断后仍沿用原始几何数量

### 现象

武汉空间总览导出前有 201 个几何要素，但受 GeoJSON 字节上限影响，文件只保留了部分要素；旧结果仍报告 `truncated=false`，前端会误以为完整几何可用。

### 根因

服务在调用有大小限制的导出器之前就根据内存中的完整 feature 列表生成几何证据，没有读取最终 artifact 的 `geometry_truncated` 和实际 features 数量。

### 修复

导出完成后重新读取受限 GeoJSON，依据最终文件计算 feature_count、sources 和 `truncated_geometry`；同时给道路/水体 feature 写入 dataset 标签，供前端分层渲染。

### 预防

空间证据必须以最终交付 artifact 为准，不能以导出前的中间集合替代。任何字节、要素数或坐标转换限制都必须进入结果状态和地图提示。

## 异步结果轮询会丢失最终 artifact 引用

### 现象

同步运行可以生成 GeoJSON，但 Console 通过异步提交和 `GET /runs/{run_id}` 轮询时，结果区没有 `geojson_ref`，地图为空；工具步骤本身仍显示成功。

### 根因

异步 worker 在服务层生成 artifact 后，持久化的 `AgentRunResult` 只包含 Runtime 基础快照，`artifact_ref` 和 `geojson_ref` 没有进入 SQLite/进程状态。异步提交响应和终态结果因此不完整。

### 修复

运行快照增加可选交付引用；服务完成 artifact/GeoJSON 导出后回写快照，SQLite 恢复也读取这些字段。未生成引用时保持字段省略，兼容原有同步契约。

### 预防

异步接口验收必须使用包含 artifact 和地图结果的请求，检查提交、轮询、服务重启后的最终响应，而不能只验证 status 和工具步骤。

## 并发异步首次提交被误标为幂等复用

### 现象

两个 worker 同时提交同一个异步请求时，最终只有一个任务被执行，但两个 HTTP 响应都可能返回 `idempotent=true`。客户端无法区分“首次接受”与“重复复用”。

### 根因

SQLite 插入和 worker claim 之间存在并发窗口。首次提交创建作业后，如果另一个 worker 先完成 claim，首次调用会走 claim 失败分支；旧代码把该分支统一当成重复提交返回。

### 修复

保留“创建者”身份：即使首次创建者没有抢到执行权，也返回 `idempotent=false`；只有 `INSERT OR IGNORE` 未创建新作业的调用才返回 `idempotent=true`。任务执行仍由成功 claim 的 worker 独占。

### 预防

幂等接口验收必须同时断言 canonical `run_id`、首次/重复响应标记和实际执行次数；不能只验证重复请求复用了同一 ID。

## Windows 进程存活探测导致异步作业无法恢复

### 现象

worker 在 claim 作业后崩溃，新的服务进程启动时作业仍保持 `RUNNING`，运行快照停留在 `PLANNING`，没有被重新执行。

### 根因

Windows 下用 `os.kill(pid, 0)` 判断进程存活时，已退出进程也可能抛出 `PermissionError`。旧实现把该异常当成“进程仍然存活”，恢复逻辑因此跳过了实际已经死亡的 owner。

### 修复

Windows 使用 `OpenProcess`、`GetExitCodeProcess` 和 `CloseHandle` 查询进程退出码，仅将 `STILL_ACTIVE` 视为存活；其他平台继续使用 `os.kill`。增加跨进程崩溃后接管回归测试。

### 预防

异步重启验收必须实际杀死 claim worker，再由新服务轮询到终态；平台相关的进程探测不能只用 Unix 语义推断 Windows 行为。

## Live GIS 测试未区分 Python 环境与 GIS 环境

### 现象

真实模型元数据请求可以通过，但区域栅格 live 测试在普通 Python 进程中失败，错误为 `geopandas is required for GeoJSONAdminBackend`；同一请求在 `spatial-agent-gis` conda 环境中成功。

### 根因

live 模型开关只表达了“允许访问模型”，没有表达本地后端是否具备 GeoPandas、Rasterio 等 GIS 依赖。测试使用 `backend=local` 时，普通解释器会在行政区 schema 步骤先失败。

### 修复

真实 GIS live 测试增加 `SPATIAL_AGENT_LIVE_GIS=1` 门控，并在验收命令中显式使用 `conda run -n spatial-agent-gis`；普通 Python 只保留离线或内存后端验证。

### 预防

真实模型、真实 GIS 和网络权限是三个独立前置条件。验收必须记录解释器/环境、Planner、Backend 和 provider 状态，不能只设置一个 live 开关。

## 异步轮询未持久化最终几何证据

### 现象

worker 已生成带真实几何的 GeoJSON，但异步轮询或服务重启后结果 envelope 将 `geometry.status` 降级为 `no_geometry`；同步返回和文件本身仍然正确。

### 根因

服务在导出后只把 `geojson_ref` 写入 `AgentRunResult`，最终 artifact 的 feature_count、来源和截断状态只存在当次内存 payload。SQLite 恢复时无法重新构造这些证据。

### 修复

运行快照增加内部可选 `geometry_evidence` 字段。导出完成后写入快照，轮询/恢复时作为显式证据重新构建统一 `result.geometry`，对外响应仍不暴露内部字段。

### 预防

异步空间验收必须同时比较同步、轮询和重启后的 geometry evidence；存在 GeoJSON 引用不等于恢复后仍保留真实几何状态。

## Live provider 暂态波动导致端到端测试偶发失败

### 现象

同一真实模型空间总览请求单独运行可以完成，但与其他 live 请求连续运行时偶发返回 `FAILED`，随后重试又成功。

### 根因

provider 上游的超时、503 或结构化响应波动与本地 Planner/Runtime 失败具有相同终态，单次 live 断言无法区分暂态外部错误和确定性代码回归。

### 修复

live 总览测试最多执行 3 次独立请求；每次仍完整验证结果类型、8 步工具覆盖、工具终态和中文答案，连续失败才报告失败。默认 CI 仍不访问网络。

### 预防

live 测试应输出安全的 provider metrics/error_type，并将暂态重试与确定性 schema/backend 错误分开统计；不能通过放宽断言掩盖计划或工具错误。

## Live 计划验收固定步骤下标和结果类型

### 现象

健康预检新增后，步骤位置发生合法变化；真实模型也可能选择合法但更具体的结果类型，旧测试仍固定断言 `steps[0]` 或单一 result type，造成假失败。

### 根因

测试把可观察计划的列表位置和某一个兼容结果类型误当成稳定公共协议，未按工具 ID、语义依赖和计划声明类型读取结果。

### 修复

live 测试按工具名查找关键步骤，结果契约断言计划声明的 `output.type`，同时保留工具成功和有效像元等业务断言。

### 预防

只有专门测试顺序时才断言下标；横切 preflight 会改变位置时应验证依赖 DAG。结果类型应以显式计划契约为主，兼容类型不能硬编码成唯一值。

## Chrome CDP 烟测并行复用页面导致状态竞争

### 现象

健康、地图和总览 smoke 同时连接同一个 Chrome CDP 实例时，总览脚本偶发报告“空间总览面板未显示”，但健康和地图脚本可能仍然通过；同一版本改为串行执行后全部通过。

### 根因

各 smoke 脚本都从 `/json/list` 选择第一个 `page`，随后对该页面执行 `Page.navigate` 和 DOM 操作。并行脚本会互相导航并覆盖会话、状态和异步结果，失败断言读取到的是另一脚本的空状态，不是后端总览功能的确定性失败。

### 修复

本次验收按健康、地图、总览、会话和清空顺序串行执行；总览脚本继续使用固定 GeoJSON 断言行政区、道路和水体分层，避免把共享页面竞争误判为地图回归。

### 预防

浏览器 smoke 要么串行复用单页面，要么为每个任务创建独立 CDP page/profile；不能仅因为后端请求互不相同就并行启动共享页面脚本。失败时先记录页面 URL、状态文本和请求 ID，再区分验收器竞争与产品回归。

## 全量测试与 smoke 并行访问 SQLite 导致锁竞争

### 现象

M68 集成验证时，同时运行外部 `unittest discover` 和会在内部再次运行全量测试的 `scripts/smoke_check.py`，其中一个测试进程在 `PRAGMA journal_mode = WAL` 处报 `sqlite3.OperationalError: database is locked`，并造成多 worker 异步测试超时；单独串行执行时没有该失败。

### 根因

两条验收命令不是纯只读检查：测试会创建或迁移 SQLite 状态库，smoke 脚本还会嵌套启动单元测试。并行进程可能同时初始化同一个默认状态路径，SQLite 的 WAL 模式切换和 schema 初始化窗口会互相阻塞。该错误属于验收编排竞争，不能直接归因于异步业务实现。

### 修复

停止并行的重复测试进程，按“全量单元测试 -> smoke（内部测试只执行一次） -> 全局评测 -> 其他部署/浏览器验收”顺序串行执行；生产多 worker 契约仍单独使用临时数据库验证。M70 在 GIS conda 环境的三 worker 测试又复现了同类竞态：即使没有外层并行，多个新进程仍可能同时切换 WAL，因此 SQLite 连接初始化增加了有限次数的 `journal_mode=WAL` 锁重试。

### 预防

涉及 SQLite、artifact 或共享输出目录的验收命令必须声明是否会写状态；有嵌套测试的脚本不能与外部全量测试并行。若需要并行，必须为每个进程提供隔离的 `SPATIAL_AGENT_STATE_DB`、artifact root 和输出目录，并在结果中记录隔离路径。SQLite 生产初始化不能只依赖 `busy_timeout`，还要覆盖 WAL 模式切换本身的锁窗口。

## Docker Desktop 服务项缺失阻断生产验收

### 现象

M68 代码验收完成后执行 Docker Compose 重建时，Docker CLI 报 Linux engine named pipe `dockerDesktopLinuxEngine` 不存在；尝试启动 `com.docker.service` 又报无法打开该服务项。此时不能获得新镜像、容器或 production acceptance 结果。

### 根因

Docker CLI、Compose 文件和镜像构建配置存在，并不代表 Docker Desktop 服务已经注册、WSL2 Linux engine 已启动或当前会话可访问 engine named pipe。服务项缺失属于宿主机安装/启动状态，和项目 Dockerfile、国内镜像源及应用代码是不同故障层。

### 修复

先检查 `Get-Service com.docker.service`、Docker Desktop GUI/WSL2 状态和 `docker info`；只有 `docker info` 能返回 Server 信息后才重建 Compose。当前机器缺少可启动的服务项，未把旧容器响应当作 M68 部署证据。

### 预防

部署验收必须把 Docker CLI 可执行、Docker Desktop 服务已注册、Linux engine 可用、镜像构建成功、容器 readiness 和业务接口验证分成独立检查；任一前置失败都要报告具体层级，不能用已有旧镜像或页面 200 代替新版本证据。

## 内存模式前端会话 fallback 与后端会话 API 不一致

### 现象

本地内存模式的 Console 可以通过前端 fallback 创建“对话1”，但 `POST /sessions` 返回 `session persistence is not configured`，`GET /sessions/{session_id}/runs` 也始终为空；浏览器会话恢复 smoke 因此无法恢复选中的会话。SQLite/生产模式没有该问题。

### 根因

前端为了支持无 SQLite 的开发模式已经生成了临时会话选项，但 `AgentService` 只在内存中保存 Runtime 的多轮澄清状态，没有提供内存会话注册表、运行历史查询、清空和删除语义，导致 UI fallback 与 HTTP 契约分裂。

### 修复

内存服务增加受控会话注册表，自动登记运行使用的 session ID，并实现创建、列表、运行历史、清空和删除；`InMemoryStateStore` 增加按 session 查询和清理运行快照。SQLite 路径保持原有持久化实现，前端现在可在 memory 和 production 两种模式使用同一会话接口。

### 预防

任何前端 fallback 都必须有对应的后端契约测试；浏览器验收至少覆盖 memory 和 SQLite 两种状态后端的会话创建、切换、历史恢复与清空，不能只验证生产数据库路径。

## 文件覆盖关系 ready 不能代替像元网格对齐

### 现象

DEM 与土地利用文件存在空间覆盖关系时，健康报告的 `dem_land_use.status` 为 `ready`，但两个栅格可能使用不同 CRS、分辨率、原点或尺寸。旧能力目录仍可能把建设候选筛选标记为可用，运行时也可能在未验证像元网格的情况下进入联合分析。

### 根因

文件级覆盖检查回答的是“是否存在相交文件”，像元级分析需要更严格的 `grid_alignment` 证据。两者位于同一关系对象中，若只读取外层 `status` 就会把覆盖证据误当成可直接逐像元运算的证据。

### 修复

能力目录现在只有在 `dem_land_use.status=ready` 且 `grid_alignment.status=aligned` 时才声明建设筛选能力；Runtime 对 `get_zonal_buildability_analysis` 和 `get_zonal_constrained_buildability_analysis` 增加像元级对齐前置门控。显式网格不一致时，在工具 dispatch 前以中文失败并保留健康步骤；内存演示没有真实网格证据时继续返回原有可解释占位结果。

### 预防

所有涉及 DEM 与土地利用联合像元运算的能力，必须同时检查文件覆盖、像元网格和 CRS 证据；测试应区分 `overlap=ready` 与 `grid_alignment=aligned` 两种状态，不能只断言外层覆盖状态。

## Manifest 完整哈希校验不能混入启动健康检查

### 现象

武汉真实数据包含多个 DEM/土地利用栅格和较大的 GeoPackage。若每次 `/health/ready` 或运行时能力请求都重新计算 SHA-256，会把大文件读取成本放进普通请求，并可能造成多个 worker 同时扫描数据卷；若只看 manifest 文件存在，又容易把“有记录”误认为“当前文件已完整核验”。

### 根因

数据可读性、manifest 路径/大小/provenance 一致性和当前文件内容的 SHA-256 一致性是三个不同证据层级。启动探针需要快速、稳定的轻量检查，而发布或换数动作需要显式的完整哈希检查。原有校验结果没有清晰区分失败的哈希检查和 metadata-only 检查。

### 修复

`DatasetCatalog` 增加结构化 manifest 配置和 `manifest_required` 语义；`scripts/bind_dataset_manifest.py` 从已提交模板生成被忽略的本地绑定配置。`scripts/dataset_manifest.py --verify` 保持显式 SHA-256 入口，并支持 `--evidence-output` 输出不含绝对路径的证据摘要。健康/runtime 检查返回 `verification_mode`、`hashes_verified`、`verified_files` 和 `data_readiness`；生产入口通过 `SPATIAL_AGENT_REQUIRE_DATASET_MANIFEST=1` 开启必需 manifest 门控。

### 预防

发布新数据卷时先运行完整校验并保存 evidence，再启动带 `manifest_required` 的服务；readiness 中 `verification_mode=metadata` 只能证明绑定和轻量元数据一致，不能表述为完整哈希通过。manifest 路径保持相对路径或本地配置路径，原始数据、机器配置和 evidence 不提交到仓库。

## 直答计划绕过异步取消和超时检查

### 现象

SQLite 作业在 worker 崩溃后被新 worker 接管时，数据库中已经存在取消标记，但请求“你好”等无需工具的直答任务仍可能最终变成 `COMPLETED`，而不是 `CANCELLED`。工具型任务因为在步骤边界检查控制标记，通常不会暴露这个问题。

### 根因

Runtime 原先只在工具步骤开始前检查 `cancel` 和 deadline。Planner 返回 `direct_answer` 后会直接设置完成状态并返回，没有任何步骤边界，因此直答路径绕过了异步控制协议。

### 修复

在规划前和规划后各执行一次统一控制检查；取消或超时会进入既有 `RunCancelled`/`RunTimedOut` 状态处理，SQLite 的终态、失败分类、幂等重放和重启接管保持一致。M69 SQLite 组合矩阵新增直答取消接管回归，已验证 `CANCELLED`。

### 预防

控制检查必须覆盖规划、直答、工具 dispatch 和重试等所有可产生终态的路径，不能把“没有工具步骤”当作不需要取消/超时语义。新增 Planner 输出类型时，应至少加入异步取消、deadline 和服务重启后的状态矩阵。

## 原始栅格可读但不能直接作为联合像元分析输入

### 现象

武汉原始 DEM 和土地利用文件都能被 Rasterio 读取，也存在文件覆盖关系，但 DEM/土地利用分别混用 `EPSG:32649` 与 `EPSG:32650`，并且边界、原点、尺寸不同。若直接把“文件可读”或“存在覆盖”当作联合像元输入资格，建设候选结果会缺少可审计的共同像元网格。

### 根因

文件级健康报告和像元级计算回答的是不同问题。现有工具可以在计算过程中临时重投影 DEM，但临时重投影没有独立的版本、nodata、目标范围和 manifest 证据，也无法让能力目录明确知道当前数据已经达到可复现的共同网格。

### 修复

新增 `scripts/prepare_analysis_rasters.py`。脚本使用武汉 13 区融合边界确定目标范围，默认生成 `EPSG:32649`、30 米固定网格；DEM 使用双线性重采样，土地利用使用最近邻重采样，分别写出派生 GeoTIFF、目标网格报告和可绑定 manifest 的本地配置。原始文件不修改。真实验证得到 4562×5277 的共同网格，`grid_alignment=aligned`，建设候选工具可返回有效像元和真实候选几何。

### 预防

联合像元工具必须以派生目标栅格的对齐报告和 manifest 为输入证据；任何重投影、重采样或 nodata 策略都必须显式记录。分类栅格不能使用双线性插值，DEM 不能与分类数据共用不透明的临时数组作为唯一证据；派生层失配时继续在 dispatch 前阻止工具。

## Windows conda run 转发中文 JSON 时的 GBK 编码失败

### 现象

在 `spatial-agent-gis` 环境中执行真实数据健康检查时，Python 本身可以生成结果，但 `conda run` 在把子进程输出转发到 PowerShell 时抛出 `UnicodeEncodeError: 'gbk' codec can't encode character`。输出中包含中文数据源、版权符号或替换字符时尤其容易触发，导致验收命令看起来像业务失败。

### 根因

Windows 当前终端和 conda 转发层仍使用 GBK 编码，而 Python JSON 输出使用 `ensure_ascii=False`，将非 GBK 字符直接写入标准输出。失败发生在 conda 捕获/转发输出阶段，不代表 Rasterio、数据健康逻辑或空间分析失败。

### 修复

真实 GIS 验收的结构化摘要使用 `json.dumps(..., ensure_ascii=True)` 输出 ASCII JSON；需要阅读中文内容时再单独读取文件或使用支持 UTF-8 的终端。业务返回值仍保留 UTF-8 中文，不能为迁就验收输出而丢弃用户可读文本。

### 预防

Windows conda 验收命令应优先输出 ASCII 安全摘要，并把完整结果写入 UTF-8 JSON 文件；遇到 conda 的编码异常时，先区分“子进程执行失败”和“输出转发失败”，不要直接判定 GIS 代码回归。

## GIS 全量套件中的嵌套 smoke 偶发丢失 artifact 引用

### 现象

在 `spatial-agent-gis` 环境执行完整 `unittest discover` 时，`test_m11_smoke_check` 的嵌套 smoke 曾偶发失败：`test_sync_async_poll_and_restart_preserve_no_geometry_envelope_and_refs` 在异步终态响应中观察到 `artifact_ref` 为空。该次失败只出现一次，真实 GIS 数据测试和业务 smoke 仍通过。

### 根因判断

当前证据不足以证明业务代码确定性回归。目标测试在 GIS 环境单独连续执行 5 次通过，`test_m11` 单独执行通过，独立 smoke 通过，完整 GIS 套件再次执行也通过。现象更符合全量套件启动嵌套测试时的异步 SQLite/artifact 终态观察竞争，而不是 Rasterio、GeoPandas 或 M71 比较证据逻辑错误。

### 处理与预防

遇到该失败时，先单独运行目标测试、单独运行 `test_m11` 和完整 GIS 套件复跑，并记录 `artifact_ref`、`geojson_ref`、SQLite job status 与 worker 是否已完成；不能只根据一次嵌套 smoke 失败提交业务修复。涉及 SQLite 或 artifact 的全量验收继续保持串行，嵌套 smoke 不与外层全量测试并行运行。

## Manifest 健康摘要缺少文件名导致派生输出一致性误报

### 现象

M75 将分析就绪报告的 DEM/土地利用输出与 manifest 做一致性比对时，真实配置的 manifest 本身为 `ready`，但 `analysis_ready.output_manifest` 被报告为 `unavailable`，原因是健康检查只返回 manifest 状态摘要，没有保留 manifest 中的文件条目。

### 根因

manifest 完整校验函数返回的是面向健康探针的摘要；输出一致性检查需要的只是受控文件 basename，却误把缺少原始 `datasets` 映射当成 manifest 内容缺失。两种响应形状的边界没有在契约中明确。

### 修复与预防

健康摘要新增 `dataset_file_names`，只保留每个数据集最多 10 个 basename，不暴露绝对路径、文件哈希或机器目录；输出一致性检查兼容该摘要并继续区分 `metadata` 与 `sha256`。测试同时覆盖完整 manifest 映射、basename 摘要和文件失配，真实武汉配置验证输出匹配 `ready`。

## 派生数据配置直接验证源绑定导致合法报告误报

### 现象

M76.2 生成三层发布报告时，真实武汉分析就绪配置的 metadata、manifest 和派生输出均为 `ready`，但源绑定被报告为 `degraded`，提示源数据已变化。

### 根因

分析就绪配置会把 `dem`/`land_use` 的当前入口替换为对齐后的派生 GeoTIFF；分析报告中的 `source_binding` 却记录的是派生前原始栅格。若直接拿当前派生 catalog 验证源指纹，就会把合法的“源层与派生层分离”误判为源数据变更。

### 修复与预防

发布报告从报告内受控的源 manifest 条目重建源文件视图，使用原始相对 basename 和当前数据根目录验证源 SHA-256；输出层继续使用当前派生 catalog 与输出 manifest 做独立 SHA-256 校验。发布校验必须明确区分源 catalog、派生 catalog 和输出 manifest，不能用当前运行入口替代派生前来源。

## 空间总览的同名工具需要按调用次数验收

### 现象

真实模型的空间总览计划会对道路和水体各调用一次 `get_zonal_vector_summary`。如果评测只把工具名转换成集合，两个调用会被压缩成一个，无法证明道路和水体两个结果都被请求；如果期望列表只写一次，报告还会把第二次合法调用显示为 unexpected。

### 根因

工具名集合只能证明“至少调用过该工具”，不能表达同一工具在不同数据集参数下的多次调用。空间总览的完整契约是工具名、数据集参数、调用次数和依赖关系的组合，不能只比较去重后的名称。

### 修复与预防

M76.2.2 live baseline 和全局评测将空间总览的 `get_zonal_vector_summary` 期望项记录两次，并继续检查计划 DAG、结果类型和实际答案。后续涉及同名工具多数据集调用的能力，应在结果契约中显式声明调用次数或参数覆盖；不要用工具名称集合替代完整计划质量。

## Live GIS 首次执行偶发后端终态失败

### 现象

M76.2.2 真实武汉 live 基线第一次运行中，空间总览模型计划已经生成且 provider 指标正常，但运行终态为 `FAILED`；同一请求随后单独重试成功，最终基线连续通过。该现象只观察到一次，尚不足以证明确定性业务回归。

### 根因判断

当前证据更接近真实 GIS 进程/原生栅格或矢量执行时序波动，provider 没有返回错误，模型计划也满足 8 步结构；重复运行未复现同一失败。不能把 provider 重试掩盖成业务成功，也不能根据一次结果直接修改空间分析逻辑。

### 修复与预防

live baseline 只对 provider 暂态错误自动重试，并记录每次的错误分类、步骤状态和安全指标；工具门控、计划校验和后端执行失败单独报告。若再次出现，应优先保存失败步骤的分类、数据健康状态、进程环境和 GIS 原生错误上下文，再判断是否需要业务修复。所有复验继续使用 `spatial-agent-gis` 环境并保持串行。

## Result envelope 在导出和恢复前构建会丢失 lineage

### 现象

M76.2.3 为 result envelope 增加运行 ID、轨迹、artifact、GeoJSON 和地图图层索引后，同步结果看起来完整，但异步轮询/服务重启后的 envelope 中 `trace.available` 变为 false；同步、异步结果比较因此失败，嵌套 smoke 也会失败。

### 根因

服务原先在生成 `trace_summary`、artifact 和 GeoJSON 之前就构建 result envelope。恢复路径从 `AgentRunResult` 重新格式化时也先构建 envelope，再补 trace；新增 lineage 读取的是构建时的 payload，而不是最终运行状态。

### 修复与预防

同步、retry、`get_run` 和恢复格式化路径现在都先准备 trace/provenance、artifact/GeoJSON 与显式几何证据，再构建一次最终 envelope；临时几何证据只在构建后移除。跨入口验收必须比较同步、异步轮询、重启和 retry 的最终 envelope，并对每次运行必然不同的 run/artifact/GeoJSON 标识做明确归一化。

## Goal 内容更新不能只依赖阶段备注

### 现象

用户要求给持续开发 goal 增加“规划下一阶段时顾全项目整体、不要陷入数据细节”的约束，但当前 goal 工具只能读取 goal，或将当前 goal 标记为 `complete`/`blocked`，不能编辑一个仍在执行中的 objective。只在对话中口头补充，后续新对话可能仍只看到旧 objective。

### 根因

goal 生命周期状态与项目恢复规则由不同机制维护。goal objective 是外部状态，仓库文档才是当前项目执行约束的可审计载体；如果只更新某个阶段标题或最近任务说明，约束不会稳定传播到后续阶段规划。

### 处理与预防

将新增约束同步写入 `docs/agent-context-resume.md`、`docs/task-resume.md` 和 `docs/milestones.md` 的当前规则区，并在中文问题日志中记录接口限制。后续每次重规划先输出产品能力、架构边界、数据质量、真实模型、部署可靠性、前端体验和测试证据七维能力矩阵，再确定阶段目标；具体数据修复必须标记为系统级目标的支撑任务。不能为了修改 objective 而虚假结束当前 goal，也不能把历史阶段中的局部任务当成当前全局目标。

## Windows 进程查询失败导致 SQLite 异步任务重复接管

### 现象

全量离线验收的三 worker SQLite 幂等场景偶发出现同一 job 被恢复两次：`recovery_count=2`，`async_jobs.status=COMPLETED`，但 `agent_runs` 仍为 `PLANNING`。结果历史、轮询和 lineage 可能读到不同终态；单独运行该测试通常通过，放在大套件后更容易暴露。

### 根因

Windows `_process_is_alive` 使用 `OpenProcess` 查询 owner PID。原实现把无法打开进程、查询 API 瞬态失败或权限异常统一返回 `False`，恢复逻辑遂把仍在工作的 worker 当成已退出并允许另一个服务接管。两个 worker 随后都进入 `AgentRuntime.run`，后启动者会先写入 `PLANNING`，旧 owner 或新 owner 的完成顺序又可能覆盖运行快照。

### 修复与预防

明确获得已退出/无效 PID 时才返回 `False`；`OpenProcess` 返回访问拒绝或进程信息查询 API 失败时保守返回 `True`，避免重复执行。显式模拟死进程的 recovery 测试仍覆盖接管路径；三 worker 精确场景连续 20 次通过，离线全量 401 项和 GIS 全量 401 项均通过。异步验收必须同时检查 job 生命周期、`agent_runs` 终态、恢复次数和 lineage，不能只看 HTTP 200 或单个状态字段。

## SQLite 幂等重复提交先于运行快照写入

### 现象

多个 worker 同时提交同一个幂等键时，重复提交方可以先拿到 canonical `run_id`，但原 worker 还没有把 `AgentRunResult(PLANNING)` 写入 `agent_runs`。重复提交方立即轮询会短暂得到 `run not found`；在全量测试中还可能表现为 worker 超时或 exit code 非零。

### 根因

`async_jobs` 的幂等插入和 `agent_runs` 初始快照写入是两个事务窗口。原实现只在“创建 job”的 worker 中写快照，复用已有 job 的 worker 直接返回；SQLite 已经能证明 job 存在，但不能证明对应的运行快照已经可读。

### 修复与预防

`SQLiteStateStore.ensure_run_snapshot` 使用 `INSERT OR IGNORE`，重复提交路径在返回前补齐缺失的 PLANNING 快照，不覆盖任何并发 worker 已写入的终态。三 worker 幂等场景连续 20 次通过；后续异步验收必须同时覆盖“job 已存在、run snapshot 尚未存在”的窗口，并验证不会覆盖 COMPLETED/FAILED 快照。

## 上下文预算直接截断序列化 JSON

### 现象

上下文工程为模型输入设置字符预算时，如果先把上下文序列化为 JSON，再直接截取字符串，超长请求会得到不完整的 JSON。模型客户端可能因此无法解析上下文，问题会被误判为 provider 或模型输出故障。

### 根因

字符预算属于结构化上下文的边界约束，不能在序列化结果上做无结构截断。原实现先生成完整 JSON，超出预算后直接切字符串，可能截断字符串、转义序列或对象闭合符。

### 修复与预防

`ContextBuilder` 现在按优先级先省略工具目录、工作流和 Planner 元数据，再对请求字段做结构化裁剪，并用二分搜索保证最终序列化结果仍是合法 JSON；运行证据只记录 schema、长度、裁剪状态和请求哈希，不保存原始上下文。测试同时验证预算上限、JSON 可解析、敏感字段剔除和 Planner 消费上下文。后续所有上下文压缩器都必须在结构化对象层操作，并把 `truncated` 纳入可观测证据。

## 规则规划器按区域和功能堆叠不符合通用 Agent 目标

### 现象

复杂请求“请对洪山区进行综合空间分析……”被路由到特定的建设候选工作流，且区域短语可能被解析为“对洪山区”。如果继续为每个行政区、分析类型和自然语言表达增加规则，功能数量增长后维护成本会接近区域、功能和表达方式的笛卡尔积。

### 根因

请求中的空间实体、任务意图、约束和输出要求没有形成独立的中间表示，规则规划器把实体识别、意图判断和具体工具编排耦合在多个 `_try_*_plan` 分支中。能力目录和工具 schema 尚未成为开放式组合编排的主要输入。

### 处理与预防

总体目标已重组为通用、可组合、可解释的空间智能体。后续建设请求建模层、能力发现和组合式 DAG 编排；RuleBasedPlanner 只作为确定性兜底，LLMPlanner 与规则路径必须输出同一 `TaskPlan` 并经过同一执行边界。具体区域只作为参数解析结果，洪山区复杂问句只作为回归样例。新增能力优先扩展实体/约束 schema、工具契约、能力目录和结果类型，不再新增区域专用分支。

## 异步提交前初始化本地 GIS runtime 导致前端永久显示分析中

### 现象

复杂 GIS 请求提交后，前端一直显示“正在分析”。复现时 `POST /runs/async` 本身超过 HTTP 超时，连 `run_id` 都没有返回；服务随后也无法及时响应健康和指标请求。

### 根因

`AgentService.run_async()` 在创建异步任务并返回排队响应之前主动调用 `_runtime(planner, backend)`。本地 GIS runtime 的数据目录和后端初始化可能耗时，因此阻塞了异步提交线程，前端无法进入轮询阶段。

### 修复与预防

移除异步提交前的 runtime 预初始化，把 runtime 构造放入 worker；提交接口先持久化任务快照并返回 `run_id`，初始化或后端错误由 worker 写入可轮询的 FAILED 终态。新增回归测试验证慢 runtime 初始化时提交仍快速返回。前端验收必须分别检查提交耗时、轮询状态、步骤状态和终态，不能只观察页面文案。

## 当前并发度与 goal 描述不一致

### 现象

项目执行规则原本记录为最多 3 路并行，但用户将当前并发度调整为 1。goal objective 由创建时固定，不能直接编辑未完成 goal；如果只修改对话中的临时说明，后续恢复可能仍读取旧并发约束。

### 根因

goal 生命周期状态和仓库执行规则属于两个独立的状态来源。goal 工具不提供编辑 objective 的接口，而项目文档承担了可审计的阶段执行约束；两者的并发度发生变化时，若不统一更新当前规则，规划、工具调用和阶段验收可能继续按旧并发度执行。

### 处理与预防

已将当前有效规则改为并发度 1，并保留历史阶段的真实记录。M77 及后续任务按“全局盘点 -> 顺序实现 -> 集成测试 -> 全局重规划”执行，不启动并行子任务。goal objective 不能编辑时，不伪造完成状态；新对话优先以恢复文档中的当前有效规则为准。

## 当前并发度再次调整为 5

### 现象

用户将当前 goal 的最大并发度从 1 调整为 5，但恢复文档、总体方向和里程碑文档中仍有旧的“当前并发度为 1”表述。新对话可能因此错误地禁止本阶段并行开发。

### 根因

goal 工具不能直接编辑未完成 goal 的 objective；并发规则实际由 goal 描述和仓库中的可审计恢复文档共同承担。只更新某个阶段尾部的规划，不能覆盖文档顶部的当前有效规则；历史阶段中的并发数字也容易被误读为现行规则。

### 处理与预防

已将当前有效规则统一为最大并发度 5，并保留历史阶段数字作为历史事实。后续只有边界清晰、写入范围不重叠、可独立验收的任务才能并行，最多 5 路；共享 schema、result envelope、Runtime 状态迁移和前端核心函数必须由主线先确定契约并统一集成。每次调整并发度后，应同时检查恢复文档、总体方向、里程碑文档和实际子 agent 槽位，不能只修改一处文字。

## Planner 内部 evidence 软偏好不应提前覆盖模板 allowlist 错误

### 现象

M81.3 将行政区边界、栅格元数据、空间总览和约束建设筛选改为模板蓝图编译后，离线全量中的 workflow runtime 回归失败。测试选择了 `admin_boundary_query` 工作流，但请求文本是“查询 DEM 栅格元数据”；预期运行时先报告 `tool is not allowed by template`，实际先报 `unknown evidence options: geometry`。Smoke 因内嵌全量单测同步失败。

### 根因

`parse_spatial_request` 会把“边界/区域/地图/几何”等词抽取为 evidence 偏好。用户选择的 workflow evidence 是严格契约，应该被模板校验拒绝；但 Planner 内部从自然语言抽出的 evidence 只是软偏好。如果把该软偏好原样传入 `raster_metadata` 模板编译，模板会先因为不支持 `geometry` 失败，掩盖了真正重要的“Planner 生成的工具不属于用户选择模板 allowlist”错误。

### 修复与预防

`RuleBasedPlanComposer._template_plan` 在调用 `compile_workflow_plan` 前按模板 `evidence_options` 过滤内部 evidence；如果过滤后为空，则回落到模板默认 evidence。外部 workflow 选择仍由 `normalize_workflow_selection` 和 `validate_workflow_plan` 严格校验，不允许静默过滤。新增/调整 planner 模板化路径时，应区分“用户显式选择的 workflow 契约”和“自然语言解析得到的展示偏好”，错误优先级应先揭示工具 allowlist、结果类型和 DAG 等执行边界问题。

## 完整 live/全量矩阵不适合作为默认开发门禁

### 现象

随着真实 GIS、真实模型、比较矩阵和 Docker acceptance 增多，阶段测试如果默认跑完整 unittest、完整 GIS、完整 live baseline 和容器内 live，会造成反馈过慢、token 消耗高，也容易把问题混在大量无关场景里。例如 M81.3 精简 live 初次失败时，真正原因是未显式绑定 analysis-ready 配置导致 raw 栅格 `grid_mismatch`，而不是模板编译或模型规划错误。

### 根因

项目已经从单一 demo 演进为多入口 Agent Runtime，测试目标不同：日常开发需要快速验证共享契约，阶段收口需要离线全局评测，真实 GIS/LLM/Docker 需要分层证明环境与数据可用。如果把所有层级混成一个默认门禁，既浪费时间和 token，也降低错误定位质量。

### 修复与预防

新增 `scripts/test_profile.py` 和 `docs/test-strategy.md`。默认使用 `quick` profile（3 个核心契约 tripwire），服务 smoke 独立使用 `smoke` profile，阶段收口使用 `stage`（quick + smoke + strict global evaluation），真实数据使用 `gis-core`，真实模型只跑 `live-short` 两个代表 case，Docker 只跑 production acceptance。完整 unittest、完整 live baseline、比较矩阵和容器内 live 只在对应共享契约、真实模型评测、数据卷或部署改动时执行。阶段文档必须记录实际运行的 profile 和数据配置，尤其 live GIS 应显式设置 analysis-ready `SPATIAL_AGENT_DATASET_CONFIG`，避免把数据准备问题误判为模型或代码问题。

## 测试文件按里程碑堆叠会让默认门禁失控

### 现象

项目已有 500+ 个历史测试用例，按里程碑文件持续累加。如果默认 profile 仍按整模块执行，开发阶段会被大量历史场景拖慢，真实问题也容易被无关失败淹没。

### 根因

测试资产和默认门禁没有分层。历史测试适合作为专项诊断和完整回归，但日常开发只需要证明当前共享契约没有断裂；把整模块测试塞进 `quick` 会把“代表性验证”退化为“小型全量”。

### 修复与预防

`scripts/test_profile.py` 的 `quick` profile 改为 3 个核心契约 tripwire，服务 smoke 独立为 `smoke` profile，`stage` 再组合 quick、smoke 和严格全局离线评测；`gis-core` 也改为真实 GIS 抽样用例。完整 unittest、完整 GIS 和完整 live 仍保留，但只在改动共享 Runtime、SQLite、HTTP 契约、生产部署、真实模型评测或数据卷配置时按需运行。新增测试时先判断它属于核心 tripwire、服务 smoke、阶段验收还是专项诊断，不要默认塞入 `quick`。

## Smoke 默认嵌套全量测试会绕过 profile 分层

### 现象

即使 `scripts/test_profile.py` 已经把 `quick` profile 收敛为少量代表样例，直接运行 `scripts/smoke_check.py` 仍会默认嵌套完整 `unittest discover`。用户从 README 或旧恢复文档按 smoke 命令验证时，会再次触发 500+ 历史测试，感觉“测试例太多”，也会让服务 smoke 与完整回归的边界不清晰。

### 根因

`smoke_check.py` 早期同时承担“完整单测 + 服务冒烟”的 CI 入口职责。后续虽然增加了 profile 分层，但只在 `quick` profile 里通过环境变量跳过嵌套全量；脚本自身默认行为没有同步调整，导致绕开 profile 入口时仍然执行重型矩阵。

### 修复与预防

`smoke_check.py` 默认只运行服务 smoke，完整 unittest 改为显式 `--with-unit-tests`；`quick` 进一步收敛为 3 个核心契约 tripwire，服务 smoke 独立成 `smoke` profile，`stage` 再组合 `quick + smoke + strict global evaluation`。后续新增测试时必须先判断它属于核心 tripwire、服务 smoke、阶段评测还是专项诊断，不能通过 smoke 或 quick 间接恢复全量默认门禁。

## 模板族匹配不能替代蓝图精确匹配

### 现象

脱敏模型回放需要证明真实模型计划既属于某个 workflow template 的工具边界，又真正遵守模板 DAG 和 result reference。如果只把输出类型和工具集合匹配作为“模板通过”，模型可能省略 `{"$from": "...", "path": "..."}` 结果引用，仍被误判为符合模板。

### 根因

模板契约有两层语义：一层是模板族匹配，包括 result type、allowed tools 和 max steps；另一层是 step blueprint 精确匹配，包括 step id、工具顺序、依赖、参数键和 result reference 形状。把两层混成一个布尔值，会让评测无法区分“工具边界正确但 DAG/引用不完整”和“完全符合模板”。

### 修复与预防

模型评测新增 `workflow_template_match`，同时输出 `matched_template_ids` 和 `exact_template_ids`。fixture 显式指定 `expected_template_id` 且模板有 blueprint 时，必须进入 exact 才通过；普通回放仍允许只验证模板族匹配。后续所有模板化 planner 验收都应分别检查 allowlist/result type 和 blueprint/result reference，不能用工具名称集合替代完整计划质量。

## 模板蓝图增长会挤出 Planner 上下文

### 现象

M81.6 给 `spatial_analysis` 增加 9 步蓝图后，完整 `workflow_template_context_summary` 超过 10KB。Runtime 仍按 8KB 上下文预算构造 Planner payload，导致 `workflow_templates` section 被裁剪为 `{"omitted": true}`，复杂请求的 `plan_evidence.matched_template_ids` 和 `exact_template_ids` 变为空。

### 根因

评测和 Runtime 对模板摘要的需要不同：评测需要 `arg_shape` 来验证 result reference 精确形状；Runtime 计划上下文和计划证据匹配只需要模板 id、工具 allowlist、result type、max steps、step id/tool/dependencies/arg keys 等紧凑契约。使用同一个完整摘要会把非必要详情带入模型上下文预算。

### 修复与预防

`workflow_template_context_summary` 增加 `compact` 和 `include_arg_shape` 参数。评测默认保留完整摘要；Runtime 使用 `compact=True, include_arg_shape=False`，将模板上下文压缩到约 5.7KB，保留计划匹配必需字段并避免预算裁剪。同时 `ContextBuilder` 的安全深度放宽到 6，确保 compact 摘要里的 `step_blueprint[].arg_keys` 不被裁成 `[omitted:depth]`，否则 `exact_template_ids` 会再次失效。后续新增模板字段时，必须区分“评测精确证据”和“Planner 运行上下文”，不能把所有调试信息默认塞进模型上下文。

## 上下文预算裁剪不能先丢模板契约

### 现象

M81.4 将 workflow template 摘要注入 Planner 上下文后，复杂空间请求的 `plan_evidence.matched_template_ids` 为空。单独调用模板匹配 helper 可以识别 `spatial_analysis`，但 Runtime 实际运行时模板上下文被标记为不可用或无法匹配。

### 根因

`workflow_templates` 摘要约 7k 字符，和 `available_tools`、空间请求事实一起进入默认 8k 上下文预算时容易超限。原裁剪顺序会优先省略模板上下文，且通用安全裁剪深度过浅时还会把模板中的 `allowed_tools`、`result_types` 等数组裁成 `[omitted:depth]`。这会让 LLMPlanner 和 plan evidence 都失去最关键的模板契约。

### 修复与预防

`ContextBuilder` 将结构化安全裁剪深度从 3 放宽到 5，并调整预算省略顺序：先省略已在 system prompt 中重复出现的 `available_tools`，尽量保留 `workflow_templates`。新增测试覆盖模板摘要、Planner 上下文注入、LLMPlanner 接收模板上下文、plan evidence、SQLite 恢复和前端显示。后续新增 Planner 上下文 section 时，必须先判断该 section 是否是计划契约核心；不能只按体积大小裁掉最关键的契约信息。

## Stage profile 隐式重型化会让阶段验收再次膨胀

### 现象

quick 和 smoke_check.py 已经精简后，普通 stage 仍然运行 quick、smoke 和 strict global evaluation，而 evaluate_global.py --strict 默认还会附带脱敏模型计划评测和多轮模型回放。用户从阶段验收入口测试时，仍会感觉测试例过多，且失败定位会被服务 smoke、全局 acceptance 和模型回放混在一起。

### 根因

测试 profile 只把日常 quick 收窄了，但没有继续区分普通阶段最小验收和发布前重型门禁。stage 同时承担普通阶段收口和完整离线评测职责，导致 profile 名称看起来轻量，实际执行范围仍偏大。

### 修复与预防

新增 evaluation/cases/stage-acceptance.json，普通 stage 只运行 quick tripwire 加 3 个代表性离线验收场景；旧式重型门禁改名为显式 full-stage。evaluate_global.py 增加 --no-model-replay，让轻量 stage 能同时跳过模型计划评测和多轮回放。后续新增验收先判断属于 quick、smoke、stage acceptance、full-stage、GIS/live/Docker 还是专项测试，不能把发布前重型证据塞回普通 stage。

## 计划预览不能复用执行结果边界

### 现象

为让用户在复杂空间请求执行前查看工具 DAG，如果直接调用完整 `run()`，会提前执行 GIS 工具、生成运行 ID 或 artifact，前端还可能把预览误显示为已经完成的结果；如果前端自行根据工具名称拼 DAG，又会与 Planner 的真实计划产生漂移。

### 根因

计划生成和工具执行虽然共享同一 Runtime，但它们的副作用和证据语义不同。预览只应证明“当前请求会如何规划”，不能声称已经获得空间数据结果；DAG 的节点顺序、依赖和参数来源也必须来自统一 `TaskPlan`，不能由页面重复编排。

### 处理与预防

新增 `AgentRuntime.preview()` 和 `AgentService.preview()`，在 Runtime/Service 边界复用上下文、Planner、模板校验和计划证据，但不调用 `ToolRegistry`、不写状态、不导出 artifact。开发 HTTP 与生产 FastAPI 统一提供 `POST /runs/preview`，响应显式带 `execution.planned_only`、`tool_execution` 和 `artifact_export`。Console 只渲染响应中的 `plan`/`dag`，执行结果仍使用正式运行 envelope。后续若需要预览与执行关联，应增加受控 plan fingerprint/version，不能把 preview payload 伪装成 `AgentRunResult`。

## 配置文件有 DeepSeek 模型但进程没有可用 API key

### 现象

本地 `config/openai.local.json` 可以显示 `deepseek-v4-flash` 和 Chat Completions 配置，但服务选择 `planner=openai` 时仍可能在真正发请求前失败。检查当前进程发现 `OPENAI_API_KEY` 未注入，配置文件也不保存 key；同时当前 base URL 是 `https://opencode.ai/zen/go/v1` 网关，不是 `https://api.deepseek.com` 直连。

### 根因

模型名称、协议和 provider 地址只是客户端配置，不等于运行时已经具备认证和网络能力。`load_openai_config()` 优先读取环境变量，再读取忽略的本地配置；如果 key 只存在于另一个 PowerShell、IDE 或 Docker 环境，当前服务进程不会自动继承。网关可用也不能证明官方 DeepSeek endpoint、账户权限或模型权限可用。

### 处理与预防

保持 key 只通过环境变量、私有配置挂载或部署 secret 注入，不写入仓库。启动 live 服务前先检查 `/health` 的 `live_llm_configured` 和 `live_llm_network`，再用显式 `SPATIAL_AGENT_LIVE_OPENAI=1` 运行最小 smoke；记录 provider、wire API、模型输出校验和 token/延迟分类。默认 rule planner、CI 和 stage 不访问网络；诊断时必须区分“没有 key”“网络受限”“网关拒绝”“模型返回非法 TaskPlan”四类问题。

## 真实模型将复合空间分析误路由为单独建设筛选

### 现象

真实 `deepseek-v4-flash` 对“洪山区综合空间分析 + 建设候选筛选”第一次返回了 9 步可执行计划，但输出类型是 `constrained_buildability_result`，区域参数使用了字面量，roads/water 的 `max_features` 变成 100，建设步骤还额外依赖了健康步骤。因此它能通过基础 TaskPlan 和 ToolRegistry 执行，却没有精确遵守 `spatial_analysis` 蓝图，`plan_evidence.exact_template_ids` 为空。

### 根因

LLM Planner 的提示词先描述了“道路/水体约束建设筛选”的独立能力，模型把复合请求中的最后一个意图当成主能力；虽然运行时上下文提供了 `workflow_templates` 和 RequestFacts，但没有明确声明完整任务集合的模板优先级和参数形状。

### 处理与预防

在 `LLMPlanner` 的 system prompt 中以结构化 `sections.spatial_request.tasks` 作为判定条件：当任务同时包含 `admin_boundary/elevation/slope/land_use/roads/water/buildability` 时，必须输出 `spatial_analysis_result`，使用 9 个固定蓝图 step id/tool、`$from` 结果引用、道路/水体 `max_features=10000` 和 `filter-admin` 依赖；单独建设筛选规则不再覆盖复合工作流。修复后真实 DeepSeek preview 返回 `spatial_analysis` 的 matched/exact 双命中，真实执行 9/9 完成。后续真实模型验收必须同时检查“可执行”和“模板 exact”，不能只看 status=COMPLETED。

## Docker Compose 的 env_file 不参与 volume 变量插值

### 现象

生产容器使用 `.env.production` 注入了 `SPATIAL_AGENT_HOST_DATASET_ROOT=D:/dataset/agent`，但运行 `docker compose -f docker-compose.prod.yml up -d --build` 后，容器内 `/data` 为空，production acceptance 报告 `admin_areas`、`dem`、`land_use` 核心数据卷不可用。检查 `docker compose config` 发现 volume source 被展开为仓库内空目录 `D:\\Project\\job\\ai-agent\\data`。

### 根因

Compose 的 `env_file` 会把变量传入容器运行环境，但不会用于 Compose 文件自身的变量插值。也就是说，`volumes: ${SPATIAL_AGENT_HOST_DATASET_ROOT:-./data}:/data:ro` 在没有同名进程环境或显式 `--env-file` 的情况下会回退到 `./data`，即使容器里最终能看到 `SPATIAL_AGENT_HOST_DATASET_ROOT`。

### 处理与预防

生产重建必须使用 `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build`，或在调用 Compose 的进程环境中显式设置 `SPATIAL_AGENT_HOST_DATASET_ROOT`。production acceptance 已扩展核心数据卷检查，先验证 `/data` 中行政区、DEM、土地利用、道路和水体均可用，再运行 preview、同步执行、错误响应和异步幂等验收。后续不能只看容器环境变量，要同时检查 Compose 展开后的 bind source 和容器内文件可见性。

## 新增能力发现上下文挤掉模板契约

### 现象

在 M82.1 增加 `capability_discovery` section 后，复杂空间分析的运行仍能生成计划和执行工具，但 `plan_evidence.matched_template_ids` / `exact_template_ids` 变为空。目标测试显示 `workflow_templates` 被上下文预算裁剪掉，导致后续计划证据无法证明复杂 DAG 精确匹配 `spatial_analysis` 模板。

### 根因

`ContextBuilder` 的 8KB 默认预算此前刚好容纳 compact 模板摘要。新增能力发现时，如果在候选能力里重复展开 signals、tasks、constraints，序列化上下文会超过预算；旧裁剪顺序先丢 `workflow_templates`，于是为了给 Planner 增加一个新信号，反而移除了更稳定、更重要的模板契约。

### 处理与预防

`CapabilityDiscovery.as_context_dict()` 改为紧凑摘要：顶层保留 signals、tasks、constraints，候选列表只保留 capability id 与 priority；`ContextBuilder` 裁剪顺序调整为先裁剪 `capability_discovery`，最后才裁剪 `workflow_templates`。M82.2 增加能力目录摘要时继续收紧为“只展开候选能力”，并把默认上下文预算提高到 12,000 字符；显式小预算测试仍覆盖裁剪行为。M82.3 进一步确认复杂请求只能详细展开“选中能力”，候选排序交给 `capability_discovery`。后续新增 Planner 上下文 section 必须先评估预算优先级：稳定执行契约和模板蓝图优先级高于解释性候选证据；目标测试要同时检查新证据存在和模板 exact 未回退。

## 复杂请求的能力目录上下文不能展开所有候选能力

### 现象

M82.3 扩展 CLI/HTTP/artifact 跨入口 Harness 后，复杂空间分析请求在 Service 和 HTTP 中能正常执行并精确匹配 `spatial_analysis` 模板，但 `result.planning.capability_catalog_ids` 缺失。检查 `context_evidence` 发现 `capability_catalog` section 被上下文预算裁剪，导致跨入口结果无法稳定证明 Planner 同时看到了能力目录和工具 schema 摘要。

### 根因

复杂请求会产生多个候选能力。如果能力目录摘要同时展开多个候选能力及其工具 schema，即使默认上下文预算已提高到 12,000 字符，也会和 `workflow_templates`、RequestFacts、能力发现证据争用预算。对 Planner 来说，候选排序已经由 `capability_discovery` 提供；能力目录真正需要详细展开的是“当前选中能力”的数据门控、后端支持和工具参数边界。

### 处理与预防

Runtime 现在只把选中能力传入 `capability_context_summary()`，目录详情聚焦选中能力；候选能力列表继续由 `capability_discovery.candidate_ids` 提供。跨入口 Harness 同时断言 `capability_discovery`、`capability_catalog`、`workflow_templates` 和 `plan_identity` 在 CLI、HTTP、artifact、run detail 与 recovery 中一致。后续新增 Planner 上下文时，优先级顺序应保持：模板 DAG 契约 > 选中能力工具边界 > 候选解释证据 > 其他辅助摘要。

## 降级说明不能由前端临时推断

### 现象

复杂空间分析在内存演示后端下可以显示 `COMPLETED` 和“已完成 9 个工具步骤”，但 DEM、坡度、土地利用、道路、水体和建设候选结果实际都是数据或几何不可用。旧 Console 只能在浏览器端扫描 geometry、runtime snapshot、health result 和步骤错误字符串临时拼“降级与限制”，artifact、HTTP run detail 和 CLI 没有同一套结构化降级证据。

### 根因

“工具步骤完成”和“分析结果可信”是两层不同语义。Runtime 只统一了执行状态、lineage 和 planning evidence，却没有把数据缺失、派生层未就绪、GeoJSON 截断和工具结果中的业务错误提升为 result envelope 契约。前端临时推断会造成入口不一致：页面能提示限制，CLI/artifact/recovery 可能仍只看到自然语言答案。

### 处理与预防

新增 `spatial-agent.degradation.v1`，由 `result_contract.py` 在后端统一生成 `result.degradation` 与 `result.data.degradations`，覆盖运行状态、几何证据、工具步骤/结果错误、数据健康、analysis-ready、source binding 和 output manifest。Artifact 同步保存 `result` 与顶层 `degradation`，production acceptance 检查同步响应和 artifact 的降级证据；Console 优先渲染后端矩阵，旧响应才走兼容推断。后续新增结果类型或数据质量信号时，先扩展 result contract，再让前端按结构化字段展示，不能把可信度判断散落在页面逻辑里。

## 前端 result-type 注册表会变成第二套业务契约

### 现象

Console 虽然已经按 result type 控制结果区，但页面内部维护了一份 result type 到 raster/health/composite/map 等 panel 的映射，并且还会按工具名扫描步骤来推断某些面板是否出现。这样后端能力目录、工作流模板和 result envelope 是一套契约，前端又有另一套局部契约；新增 result type 时容易出现后端已支持、前端未注册，或工具刚好出现导致页面显示不该显示的面板。

### 根因

结果展示的“哪些区域应该出现”属于 Agent Runtime 的输出语义，而不是浏览器页面的业务判断。前端可以知道 panel 名到 DOM 的映射，但不应该根据 result type、tool name 或步骤错误去重新推理结果形态。否则 CLI、HTTP、artifact、run detail 和 Console 对同一次运行会看到不同的展示结构。

### 处理与预防

新增 `spatial-agent.workspace.v1`，由 `result_contract.py` 统一输出 `result.workspace`：包含注册状态、通用 panel、结果专属 panel、主 panel 和地图可用性。Console 删除前端 result-type registry，不再按工具名推断面板；它只把后端给出的 panel 名映射到已有 DOM 区域，工具结果只负责填充已打开的 panel。Production acceptance 检查同步响应与 artifact 的 workspace schema。后续继续把 panel 内部 metrics/table/chart/map payload 结构化，减少前端扫描 `steps` 生成展示内容。

## 面板内部指标不能由前端扫描 steps 推断

### 现象

M83 以后 Console 已经由后端 `result.workspace.panels` 决定哪些结果面板出现，但面板内部内容仍由浏览器扫描 `steps` 生成：栅格面板查找 `statistics/metadata`，空间总览面板临时统计 dataset 集合和 geometry 状态。这样虽然面板开关是后端契约，指标、说明、地图 bounds 仍是前端第二套业务判断。

### 根因

“哪些面板出现”和“每个面板显示什么”是同一类结果语义。如果只把前者下沉到 Runtime，后者留在页面里按工具结果猜测，CLI、HTTP、artifact、run detail 和 Console 仍可能不一致；新增工具或 result type 时，前端容易因为字段形状相似而展示错误指标，或者 artifact 中缺少可复现的展示数据。

### 处理与预防

新增 `spatial-agent.views.v1`，由 `result_contract.py` 统一输出 `result.views.panels`：先覆盖 `raster_metadata`、`raster_statistics`、`spatial_overview` 和 `map` view，再扩展 `dataset_health`、`spatial_composite` 和 `buildability_screening`，包含有界 metrics、来源 step、说明、分布、覆盖率、rows/categories/coverage 和栅格/GeoJSON 预览证据。Console 改为消费 `resultViewPanels(data)` 和 `renderMetricGrid()`，栅格、总览、健康检查、综合分析和建设筛选都不再扫描 `steps` 或工具名自行推断指标。Production acceptance 增加 `Assert-ViewEvidence`，同步响应与 artifact 都必须保留同一 views schema；artifact viewer 也改为渲染 `result.views.panels`，让 artifact 成为可复现展示 payload。后续新增 vector/table/chart 展示时，应先扩展 backend view model 和 result contract 测试，再让前端按结构化 view 渲染，不能把面板内部语义继续散落到页面逻辑。

## Artifact fallback 恢复不能重建丢失展示契约

### 现象

M86 将 `result.views` 纳入 direct service、HTTP `/runs`、HTTP run detail、CLI、artifact 和 artifact fallback recovery 的跨入口一致性 Harness 后，发现普通 HTTP 运行和 artifact 中都有 `views.panels`，但重启/新服务通过 artifact fallback 恢复同一 run detail 时，`result.views.panels` 变为空。

### 根因

artifact fallback 读取的是持久化运行记录，其中已经包含最终 `result` envelope；但 `AgentService.get_run()` 旧逻辑会再次调用 `build_result_contract(payload)`。当 artifact payload 不再携带足够完整的原始工具 `steps` 或几何中间态时，重新构建只能得到基础 envelope，无法恢复原来由工具结果派生出的 panel view payload。

### 诊断

运行 `tests.test_m81_plan_evidence_acceptance`，比较 `_normalized_contract(http_run)` 与 `_normalized_contract(recovered)`。如果只有 recovered 的 `view_panels` / `view_kinds` 为空，而 HTTP 和 artifact 正常，问题就在 artifact fallback 恢复路径。

### 修复与预防

`AgentService.get_run()` 在 artifact fallback 路径中先保存 artifact 里的 `result`，重建基础 contract 后，如果原 artifact 已有 `result.views`，则保留该 views envelope。这样旧 artifact 仍能重建基础结果，新 artifact 不会丢失展示契约。后续新增任何 result envelope 子契约时，都要把 direct/HTTP/detail/CLI/artifact/recovery 加入同一 normalization Harness，不能只验证同步响应或 artifact 文件本身。

## 矢量结果不能回退为原始 JSON 展示

### 现象

M88 之前，`vector_result`、`zonal_vector_summary_result` 和 `spatial_relation_result` 虽然已经由后端 workspace contract 打开结构化结果区，但面板内部没有后端 view payload。Console 只能显示整个 result envelope 的 JSON fallback，用户会看到技术字段而不是要素数、数据集、行政区、分类计数等可读结果；artifact viewer 和 HTTP/CLI 也缺少同一套可复现展示语义。

### 根因

矢量查询、区域矢量摘要和空间关系结果属于同一类“表格/摘要型空间结果”，但此前没有收敛到 `result.views.panels`。如果前端为了好看再扫描 `steps` 或工具名生成表格，就会重新制造第二套业务契约，且不同入口仍然不一致。

### 处理与预防

`result_contract.py` 新增 `vector` view：`range_query` 输出 `vector_query`，`get_zonal_vector_summary` 输出 `zonal_vector_summary`，`spatial_join` 输出 `spatial_relation`；只暴露有界 metrics、rows、分类 table 和 result_ref，不内联原始几何。Console 结构化结果区优先渲染 `resultViewPanels(data).vector` 和 `renderViewTable(view.table)`，没有 vector view 时才回退 JSON。后续 table/chart 也应先扩展 backend view model 和 result contract 测试，再让前端渲染结构化 payload，不能在页面端按工具名重建业务语义。

## Artifact viewer 不能只渲染 view metrics

### 现象

M88 后 `result.views.panels.vector` 已经包含 `rows` 和 `table`，Console 能展示数据集、行政区和分类计数，但 artifact viewer 的 `Result Views` 区块仍只渲染 metrics/note。这样 artifact 虽然保留了 payload，却不能作为可复现展示面，用户打开 HTML 时仍看不到矢量分类表。

### 根因

Artifact viewer 是 Console 之外的独立展示入口。如果它只跟进 schema 名和 metric card，而没有通用 rows/table 渲染，就会让 `result.views` 的一部分展示语义只在浏览器 Console 生效，跨入口一致性不完整。

### 处理与预防

`agent/artifact_viewer.py` 增加通用 `_view_rows()` 和 `_view_table()`，对任意 panel 的 rows/table 做 HTML escape、行列裁剪和自包含渲染。M17 测试覆盖矢量分类 table 和 `<water>` escape。后续新增 chart 或更复杂 view payload 时，artifact viewer 也要同步消费同一 `result.views` contract，不能只在 Console 里实现可视化。

## 对比图不能由前端独自定义业务语义

### 现象

M90 之前，阈值对比、多区域对比和道路距离约束对比的 endpoint 直接返回 `results` rows，Console 负责计算峰值、拼表格和绘制条形条。虽然运行结果可用，但 chart/table 的展示语义没有进入 `result.views`，artifact viewer、HTTP 客户端和后续跨入口验收无法复用同一套图形 payload。

### 根因

比较型结果本质上也是 Agent 输出语义：x/y 字段、series、table 列、指标和单调性说明都应由 Runtime/Service 边界统一给出。如果继续由页面扫描 rows 自行推断，Console 会再次成为第二套业务契约，和 result envelope 的方向相反。

### 处理与预防

新增 `build_comparison_views()`，由后端统一生成 `views.panels.chart`，包含 `kind=comparison_chart`、`chart_type=bar`、`encodings`、有界 `series.points`、`table` 和 `metrics`。三个 comparison service 返回同一 views schema；Console 优先渲染 chart view，旧 rows 表格只做 fallback；artifact viewer 同步渲染 chart series。后续新增任何趋势图、敏感性图或矩阵图，都应先扩展 backend view model 和测试，再让展示入口消费该 payload。

## 生产验收不能把空 view panel 误判为契约错误

### 现象

M91 运行 Docker production acceptance 时，同步内存 admin boundary 请求返回 `COMPLETED`，但 `result.workspace.panels` 与 `result.views.panels` 都为空。旧 `Assert-ViewEvidence` 遍历 PowerShell `PSObject.Properties.Name` 时得到空属性名，随后报错 `sync run view panel not declared by workspace:`。

### 根因

空 `views.panels` 是合法结果：有些内存演示后端或降级路径没有可展示的结果专属 panel，只保留 answer、trace、planning、degradation 等通用证据。生产验收脚本把 PowerShell 的空属性名当成真实 panel 名，等价于在验收层制造了一个不存在的业务契约。

### 处理与预防

`production_acceptance.ps1` 先用 `IsNullOrWhiteSpace` 过滤 `$viewPanelNames`，再验证每个非空 view panel 是否出现在 `result.workspace.panels`；验收摘要 `sync_view_panels` 同样过滤空名。`tests/test_m66_data_volume.py` 增加静态门禁。后续生产验收只能拒绝“存在但未声明”的 view panel，不能要求每个结果都必须有专属 view panel，更不能为了脚本通过让后端伪造空展示面板。

## PowerShell 中文 JSON 请求体会影响生产手工验收

### 现象

M91 手工验证生产 `/runs` 时，直接在 PowerShell 字符串里写 `查询洪山区行政区边界` 曾导致请求进入后端后变成 mojibake，Planner 无法识别行政区和任务意图，返回 `NEEDS_CLARIFICATION`。同一请求改用 JSON unicode escape 后正常返回 `admin_area_result`、GeoJSON/map view 和 1 个行政区要素。

### 根因

问题发生在手工 CLI 请求构造层，不是 Planner、ToolRegistry 或 GIS backend 的语义错误。Windows PowerShell、控制台代码页和 JSON body 编码不一致时，中文请求在到达 HTTP 服务前已经被破坏；如果把这种结果当作模型或规则 Planner 问题，会误导后续修复方向。

### 处理与预防

生产手工验收中文请求优先使用 JSON unicode escape，或显式用 UTF-8 编码构造请求体。文档和验收记录必须区分“编码导致的输入损坏”和“Planner 不能理解请求”。后续若新增 CLI/API smoke 脚本，应统一提供 UTF-8-safe 的请求构造函数，而不是在每个手工命令里直接拼中文 JSON。

## 工具数量增长不等于应立即用 MCP 替换 ToolRegistry

### 判断

当工具数量增加时，真正需要稳定的是工具定义、schema 校验、参数边界、权限、数据依赖、错误分类、trace 和结果契约；MCP 主要解决跨进程或跨系统发现/调用，不会自动解决这些 Runtime 语义。

### 处理与预防

M92 新增 `ToolProvider` seam：`NativeToolProvider` 接入现有 JSON schema 和进程内 adapter，`MCPToolProvider` 只作为未来外部来源 adapter。ToolRegistry 仍是唯一 dispatch 边界，provider 不能绕过 schema 校验、动态工具规则、degradation、workspace/views 或 artifact。只有出现实际的远程 GIS、数据库或第三方工具需求时，才实现 MCP adapter，并用同一 Registry contract 验收，避免引入一个与内部工具平行的第二套系统。

## Docker 服务存在但无法打开 engine 时不能复用旧容器证据

### 现象

M92 尝试用当前代码重建生产容器时，Docker CLI 报 `dockerDesktopLinuxEngine` named pipe 不存在；PowerShell 查询显示 `com.docker.service` 为 Stopped，但 `Start-Service -Name com.docker.service` 又报无法打开该 service handle。

### 处理与预防

将该问题视为宿主部署环境故障，而不是 Agent Runtime 或 ToolProvider 失败。离线测试、quick/stage 和静态契约可以继续执行，但不能把旧容器的 health、production acceptance 或 live 响应当作当前提交证据。环境恢复后必须用当前代码重建镜像，再重新执行 readiness、数据卷、同步/异步和 provider 证据验收。

## Provider 治理摘要重复展开会挤掉能力目录契约

### 现象

M93 在 Planner 上下文中同时展开 provider 健康、完整治理工具列表和工具 schema 后，复杂空间请求虽然仍能执行，但 `capability_discovery` / `capability_catalog` 被上下文裁剪，跨入口计划证据缺少选中能力信息。

### 根因

治理信息和工具 schema 存在重复：权限、数据依赖和审批信息在每个工具 schema 中已经足够表达，若再把全部工具治理条目复制到独立 section，会与工作流模板争用固定上下文预算。ContextBuilder 的裁剪顺序如果不区分“执行契约”和“解释性摘要”，新增 provider 证据会破坏已有规划证据。

### 处理与预防

M93 将独立 `tool_governance` section 收紧为统计摘要，权限和数据依赖只保留在选中工具 schema；ContextBuilder 默认预算调整为 16,000 字符，并按“能力发现 -> 能力目录 -> 工作流模板”的顺序裁剪，工作流模板优先级最高。新增 Planner 上下文 section 必须先检查是否与现有 schema 重复，并用复杂请求测试确认 `capability_discovery`、`capability_catalog`、`workflow_templates` 和 plan evidence 同时存在。

## RequestFacts 只放在 Planner context 会造成恢复与展示契约断裂

### 现象

M95 之前，`parse_spatial_request()` 已经抽取了行政区、任务、数据集、约束和证据，但这些 facts 主要只存在于 Planner 的临时 `spatial_request` section。同步结果、preview、SQLite recovery、artifact 和 result envelope 没有同一个版本化 RequestFacts 引用，跨入口无法证明“同一请求被同样理解”。

### 根因

请求抽取、能力发现、工作流约束和结果展示分别保留了相似字段；如果不把 RequestFacts 固化为运行快照，后续入口可能重新解析已被拼接/澄清过的文本，或者由前端从 plan/steps 反推原始意图，形成第二套语义。

### 处理与预防

新增 `spatial-agent.request-facts.v1`，Runtime 在规划前生成一次 `RequestFacts`，并将无原文的 context-safe projection 同时写入 `AgentRunResult`、preview、result envelope、SQLite 和 artifact；`plan_evidence` 记录 schema version 与受限摘要。后续新增请求字段必须先进入 RequestFacts，再由 CapabilityCatalog/WorkflowTemplate/Result contract 消费，不能在页面、工具或答案组合器中重复解析自然语言。

## 规划证据与执行门控不能各自维护工具治理副本

### 现象

如果 Planner context、plan evidence、Runtime preflight、StepRun 和 artifact 各自读取工具权限、数据依赖或 timeout，治理配置修改后可能出现“计划显示允许、执行时拒绝、artifact 没有解释”的不一致。

### 处理与预防

M95 让 `ToolRegistry.governance_for()` 成为唯一治理读取 seam：plan evidence 输出 `spatial-agent.execution-policy.v1`，每个实际 StepRun 保存同一治理快照，result evidence、SQLite、artifact 和 step observability 复用该快照/错误码。未来治理字段必须先扩展 Registry contract，再同步各入口的 normalization 测试，不能从前端或模板重新推断权限。

## 工具级 timeout 不能替代 run 级协作式超时

### 现象

M94 为 Registry 接入 per-tool timeout 后，最初把 run 的剩余时间也传成工具 timeout。已有取消/超时测试随即出现正在执行的步骤仍为 `RUNNING`，或者工具内部 timeout 被 Runtime 当成普通失败，最终状态变成 `FAILED` 而不是 `TIMED_OUT`。

### 根因

两个 timeout 的职责不同：工具级 timeout 是 provider dispatch 的有界等待；run-level timeout 是 Runtime 在步骤边界检查的协作式预算。把 run 剩余预算包装成工具级 timeout，会改变原有状态机和步骤完成语义，且线程无法安全强制终止正在执行的 Python/native/provider 调用。

### 处理与预防

Registry 只对工具声明的 `timeout_seconds` 建立有界 dispatch 等待；Runtime 的 `timeout_seconds` 继续只在规划、步骤开始和步骤结束边界检查。若未来需要让工具 timeout 触发 run 的 `TIMED_OUT`，必须先设计统一的错误分类转换和步骤状态迁移，并增加同步/异步/取消/重启恢复矩阵，不能仅修改一个 timeout 参数的传递方式。

## 可替换 ToolProvider 不能只验证 invoke 接口

### 现象

M92 之后，非 Native provider 只要提供 `definitions()` 和 `invoke()` 就可以接入 Registry。如果 provider 返回错误的工具名、非 object 的输入 schema、治理字段类型错误或无效 timeout，问题可能直到 Planner 生成计划或实际 dispatch 时才暴露；这会让“provider 可替换”变成只替换调用实现，却没有稳定的工具契约。

### 根因

Provider 是工具来源适配器，不应决定 Runtime 如何解释工具定义。若 Registry 只复制 provider 的 definitions 而不在接入 seam 做合同校验，schema 校验、权限门控、上下文摘要和生产健康状态会分别看到不同程度的无效元数据。引入 MCP 也不能解决这个问题，因为 MCP 只提供外部工具传输协议。

### 处理与预防

M96 在 `ToolRegistry` 构造时统一调用 `validate_tool_definitions()`，校验工具名、输入/输出 object schema、name 与目录 key、一组治理字段和正数有限 timeout，并生成 `spatial-agent.tool-provider-contract.v1` 安全证据。provider 健康、runtime capability、Planner plan evidence 和生产 acceptance 都保留该合同状态；非 Native provider 的回放仍经过同一 Registry、权限、timeout、StepRun governance 和结果契约。后续实现 `MCPToolProvider` 时必须先通过同一合同，不能把协议客户端直接暴露给 Planner 或 Runtime。

## 运行级失败只保留字符串会使恢复入口无法解释失败

### 现象

M95 之前，StepRun 已经有 `error_category` 和 `error_code`，但运行级结果主要只有向后兼容的 `error` 字符串。同步结果、HTTP 响应、异步轮询、SQLite 恢复和 artifact 可能只能通过文本猜测失败发生在规划、执行还是控制阶段；真实 provider 的 retryable 属性也无法稳定传递到运行级证据。

### 根因

步骤失败和运行失败是两个层次。Runtime 可能先遇到工具门控、再触发重规划，或者在规划、取消、超时阶段直接结束。如果每个入口自己从错误文本推断分类，字符串措辞变化就会造成前端状态、恢复策略和评测结果不一致。错误原文还可能包含 provider URL、token 或本地路径，不适合作为跨入口机器契约。

### 处理与预防

M97 新增 `spatial-agent.failure.v1`，运行级 `failure` 只保存 status、category、code、phase 和 retryable，不复制原始错误文本；旧 `error` 字段继续保留给人读。Runtime、service formatting、result envelope、artifact、SQLite recovery、HTTP 和生产 acceptance 共用该结构，并为旧运行 payload 提供安全 normalization。后续新增失败状态必须先定义机器 code/category/phase，再补前端文案或重规划策略，不能让入口解析错误字符串。

## 失败契约落盘但不进入 trace 和前端仍然不可观测

### 现象

M97 已将 `failure` 写入运行结果、artifact 和 SQLite，但 JSON-lines run span 只保留旧的 `error_category`，Console 也只显示人读错误文本和分类徽章。排查异步 worker 或 provider 故障时，仍需打开原始 JSON 才能知道错误码、阶段和是否可重试。

### 处理与预防

M98 将 `error_code`、`failure_phase`、`failure_retryable` 加入 observability 的 allowlist，并由 Runtime 从版本化 failure evidence 填充；原始错误文本仍被禁止进入事件。Console 增加受限 failure badge，显示阶段、错误码和可重试性。以后新增机器契约字段必须同时检查持久化、trace 和至少一个用户可读消费面，不能只增加后端字段。

## 自适应重规划只保留顶层事件会造成结果入口语义分叉

### 现象

Runtime 已将自适应重规划写入顶层 `replan_events`，artifact 和 observability 也能记录重规划次数，但 `result` envelope 和 lineage 没有同一份版本化证据。HTTP 客户端、artifact recovery 和 Console 因而可能分别读取顶层字段或自行推断，无法用统一契约说明哪个步骤失败、替代了哪些步骤以及重规划是否发生。

### 根因

重规划既是执行控制事件，也是用户需要理解的结果证据。只在 `AgentRunResult` 或前端保留事件，会使结果 envelope 仍然只表达“最终成功/失败”，调用方不得不依赖实现细节；旧 artifact、异常 planner 或外部 provider 还可能提交未受限的事件字段。顶层事件没有经过结果 seam 的二次校验时，跨入口的字段边界也不一致。

### 处理与预防

M99 新增 `spatial-agent.replanning.v1`，由 `result_contract.py` 统一校验并限制事件数量、步骤标识、替代步骤数量、延迟和时间戳；原始异常文本不会进入该契约。`result.replanning` 与 `result.lineage.replanning` 共用这份证据，Console 优先读取 result envelope，旧顶层 `replan_events` 只作为兼容 fallback；可读 trace 同时说明自适应重规划。以后新增执行控制事件必须同时检查 result envelope、lineage、持久化恢复、trace 和前端消费面，不能只增加一个顶层列表。

## Live GIS 验收未显式绑定数据配置会把数据问题误判为代码失败

### 现象

真实模型 + 本地 GIS 总览测试第一次运行时，连续三次在 `get_zonal_vector_summary` 的数据预检处失败，提示 `roads` 不可用。实际 `D:\tmp\wuhan-gis\wuhan-osm.gpkg` 和分析就绪 manifest 都存在；给进程显式注入正式的 `datasets.wuhan.analysis-ready.bound.json` 后，同一测试成功。

### 根因

`build_runtime("openai", "local")` 会从 `SPATIAL_AGENT_DATASET_CONFIG` 读取本地数据目录。手工执行 live 测试时只设置了模型/GIS live 开关，没有设置 bound 配置，于是运行时回退到仓库示例配置；示例配置没有真实道路文件，数据门控按设计拒绝工具。这个失败属于配置/数据前置条件，不是 LLM 规划、ToolRegistry 或 MCP 问题。

### 处理与预防

真实 GIS 验收必须显式设置 `SPATIAL_AGENT_DATASET_CONFIG`，或使用 `scripts/test_profile.py --profile live-short --dataset-config D:\tmp\wuhan-gis\datasets.wuhan.analysis-ready.bound.json`。M100 让 `live-short` 的本地 GIS 模式在启动前拒绝缺少该配置的命令，避免回退到示例数据。验收记录同时保留 planner、backend、dataset config 和数据健康状态；不能因为模型请求失败就放宽 roads/water 数据门控，也不能把缺少配置的失败算作当前代码回归。

## 生产验收脚本落后于结果契约会漏掉新证据

### 现象

M99 增加了 `result.replanning` 和 `result.lineage.replanning`，但生产 acceptance 最初只检查 planning、degradation、workspace、views 和 failure。即使生产入口丢失重规划证据，静态 acceptance 也可能继续通过。

### 根因

结果契约是持续演进的；如果每次新增版本化证据只补单元测试而不更新生产验收，Docker、HTTP、artifact 和恢复链路的门禁会出现覆盖空洞。前端或单元测试通过不能证明生产脚本实际读取了同一字段。

### 处理与预防

M101 新增 `Assert-ReplanningEvidence`，生产同步结果和 artifact 必须校验 schema、事件数量、字段边界和 lineage 计数一致；静态契约测试同时检查函数和调用点。以后新增 `result.*` 版本化证据时，必须同步更新生产 acceptance、artifact/recovery 验证和至少一个跨入口测试，不能只修改结果构造器。

## 旧 artifact 只保留嵌套结果时重规划证据可能丢失

### 现象

当前运行结果同时保留顶层 `replan_events` 和嵌套 `result.replanning`。如果旧 artifact 或外部结果生产者只保存嵌套结果，恢复入口重新构造 result envelope 时只读取顶层字段，可能把已有的重规划事件重建为空。

### 根因

结果契约演进过程中，顶层兼容字段和版本化 envelope 的生命周期不一定同步。恢复逻辑若只依赖当前 Runtime 的写入形状，就会把 artifact 结构当成固定实现细节，削弱可替换存储和历史恢复能力。

### 处理与预防

M102 在 `result_contract.py` 增加统一读取 seam：优先读取顶层 `replan_events`，缺失时回退到 `result.replanning.events`，之后仍经过同一有界归一化。新增 artifact round-trip 和 legacy nested result 回归，确保恢复后的 result 与 lineage 证据一致。后续版本化字段迁移必须同时设计当前写入、旧 payload 回退和 artifact/recovery 测试，不能只更新 writer。

## HTTP 结果 envelope 的顶层兼容字段与嵌套字段容易被误读

### 现象

M103 本地 HTTP 验收中，响应顶层同时存在兼容字段 `result_type` 和统一的 `result` envelope。`result_type` 在顶层可直接读取，而 `result` 内使用 `type`、`views`、`workspace` 等契约字段；如果验收脚本错误读取 `result.result_type` 或 `result.result.views`，会误报“结果类型/视图缺失”。

### 根因

为了兼容旧客户端，运行响应保留了顶层字段；新结果契约则把跨入口证据集中在 `result` envelope。两套字段形状同时存在时，人工验收容易把兼容字段名称和 envelope 内字段名称拼接使用。

### 处理与预防

结果契约验收统一使用 `result.type`、`result.views`、`result.workspace`、`result.lineage` 和 `result.replanning`；只有兼容性断言才读取顶层 `result_type`、`replan_events` 等旧字段。生产 acceptance、artifact recovery 和前端消费必须保持同一读取规则，不能通过字段名称相似性推断嵌套路径。

## 隔离 Chrome CDP headless 进程退出导致动态 Console 验收无法启动

### 现象

M103 启动独立临时 profile 的 Chrome headless CDP 时，Chrome 可执行文件存在，但进程在本机退出码 13，`127.0.0.1:9223/json/version` 未监听；应用 HTTP 服务本身可正常启动。已有 Chrome 进程存在，但没有可复用的 CDP 端口。

### 根因

当前没有足够证据确认是 Chrome 版本、宿主策略、启动参数还是现有浏览器进程环境导致；这是浏览器验收宿主问题，不应归类为前端运行时失败。

### 处理与预防

本轮不修改业务代码，也不终止用户已有 Chrome；动态浏览器 smoke 标记为未执行，静态前端契约和既有浏览器测试继续作为离线证据。后续使用隔离 profile、显式 CDP 参数或可控浏览器运行环境重新验收，并在 CDP 真正监听后才记录动态通过；不能把 CDP 启动失败当作 Console 功能通过。

## 直接调用 AgentRuntime 不能替代 Service/HTTP result envelope 验收

### 现象

M106 真实模型 + 本地 GIS 开放式查询中，直接调用 `AgentRuntime.run()` 得到的 `AgentRunResult.to_dict()` 没有 `result.type`、`workspace` 和 `views`；同一个请求通过 `AgentService.run()` 后，返回完整的 `zonal_vector_summary_result` envelope、vector workspace/views 和真实道路/水体摘要。

### 根因

`AgentRuntime` 是规划、执行、观测和状态的内部编排 seam，`AgentRunResult` 是内部运行对象。跨 HTTP、CLI、artifact、recovery 的用户结果由 `AgentService` 的格式化层补充 `result_contract.py`、trace、provenance、GeoJSON 和兼容字段。将内部对象误当作外部结果，会把预期的分层误报成结果契约缺失。

### 处理与预防

真实入口验收必须通过 `AgentService`、HTTP 或 CLI，并检查 `result.type`、`result.workspace`、`result.views` 和 lineage；Runtime 单测只验证内部状态机和 `AgentRunResult`。如果未来要求 Runtime 直接输出外部 envelope，应先明确新的接口契约并同步 artifact/recovery/前端，而不能在验收脚本中拼接字段路径。

## Windows CI 的 stage profile 被子进程输出编码阻塞

### 现象

GitHub Actions 的 CI run 在服务 smoke 成功后，于 `Run stage contract profile` 失败，完整离线 unittest 因前一步失败而被跳过。GitHub check 可确认失败步骤和退出码，但当前凭据没有读取 Actions 原始日志的权限；本地使用 Python 3.14 运行同一 profile 则通过。stage 报告包含中文验收类别，且由 profile runner 通过 `subprocess.run(..., text=True)` 捕获子进程输出。

### 根因

Windows runner 的默认 locale/stdio 编码不应被当作 Python 子进程 JSON 输出的契约。stage runner 原先没有显式指定 `encoding`，子进程也没有统一使用 UTF-8；在 Python 3.11 的 GitHub Windows 环境中，locale 差异可能在报告捕获或输出阶段将一个业务通过的 stage 误判为进程失败。这个问题属于 CI harness 的跨平台编码边界，不是 Agent Runtime、Planner 或空间数据失败。

### 处理与预防

`scripts/test_profile.py` 现在为子进程设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`，并以 UTF-8（带替换错误处理）捕获 stdout/stderr；GitHub workflow 同时在 job 级声明这两个环境变量。`tests/test_m81_test_profiles.py` 增加中文子进程输出回归。stage profile 仍保留，因为它提供少量代表性 Runtime 契约验收，不能为了绕过 CI 失败而删除。

以后 CI/测试 harness 只要跨进程读取机器可读输出，就必须显式指定编码并覆盖至少一个非 ASCII 回归；报告输出编码问题要与业务测试失败分开诊断。Actions 日志不可读时，应至少先读取 job steps/check annotations，再用本地等价命令复现，不能仅凭 “All jobs have failed” 删除门禁。

## 跨入口验收各自复制结果投影会造成契约漂移

### 现象

CLI、HTTP、artifact 和 recovery 的回归都需要判断“是否使用了同一 Runtime 契约”。原先这类测试在单个测试文件内手工读取 `result.type`、planning、views、lineage 和步骤治理字段；新增字段或兼容字段迁移时，不同测试可能选择不同的忽略规则，测试仍然通过但无法证明入口一致。

### 根因

结果 envelope 的稳定字段与 transport-specific 字段没有单独的测试 seam。测试调用方知道了太多内部字段路径，导致投影逻辑变浅且分散；这既增加维护成本，也让前端/HTTP/artifact 的契约变化无法集中发现。

### 处理与预防

M108 新增 `evaluation/contract_harness.py`，以 `normalize_result`、`compare_results` 和有界差异路径作为统一接口，集中筛选答案、RequestFacts、planning、治理、步骤、trace、workspace、views 和 artifact 可用性，同时忽略 run id、路径和时间等传输字段。跨入口测试统一使用该 Harness；以后扩展 result envelope 时，先更新 Harness 和跨入口回归，再修改单个入口断言。

## 异步服务把 Runtime 中间终态暴露给 artifact 轮询

### 现象

异步请求同时要求 `export_artifact=true` 和 `export_geojson=true` 时，偶发出现 `get_run()` 已返回 `COMPLETED`，但 `artifact_ref`/`geojson_ref` 为空；同一时刻直接读取 SQLite 的 `agent_runs` 已经包含两个引用，artifact 文件也可在随后看到。该问题在完整回归中表现为 `test_async_artifact_references_survive_polling_and_recreation` 偶发失败。

### 根因

`AgentRuntime` 会先把工具执行完成后的 `COMPLETED` 快照写入共享 SQLite，`AgentService` 随后才导出 artifact/GeoJSON、补齐引用并保存最终快照。轮询器按 run status 判断终态时，可能在这两个写入之间读到中间快照；async job 的最终标记并不能撤回已经返回的旧结果。

### 处理与预防

M108 让 `AgentService.get_run()` 根据 async job 原始请求判断是否要求 artifact/GeoJSON；如果运行已完成但所要求的引用尚未出现在快照中，继续等待最终化窗口（有界 5 秒）后再返回。新增逻辑只影响持久化异步且明确请求导出的运行，不改变同步或不导出的结果。以后新增异步结果引用时，必须把“请求要求的引用、运行终态、最终快照和轮询响应”作为一个原子可观察契约测试，不能只校验 worker 最终状态。

## PowerShell 生产验收直接调用 Python Harness 的边界

### 现象

M110 将生产 `production_acceptance.ps1` 接入统一 Contract Harness 时，直接执行 `scripts/contract_harness_check.py` 最初无法导入仓库内的 `evaluation` 包；同时，PowerShell 把对象数组通过普通管道传给 `ConvertTo-Json` 时，可能将多个 payload 序列化为多个 JSON 文档，而不是一个可供 Python 读取的 JSON 数组。

### 根因

直接执行位于 `scripts/` 下的 Python 文件时，Python 默认把脚本目录而不是仓库根目录放在导入路径中。PowerShell 管道会枚举数组，`ConvertTo-Json` 的输入形状因此取决于调用方式；这两个边界问题都不是 Agent Runtime 业务失败，却会让生产验收在真正请求 API 之前失败或无法比较结果。

### 处理与预防

M110 在 `contract_harness_check.py` 中显式加入仓库根目录导入路径，并支持单个 JSON 数组文件；PowerShell 使用 UTF-8 临时文件和 `ConvertTo-Json -InputObject @($payloads)`，再由同一 Python Harness 比较同步结果与 artifact。新增了等价、差异、真实 Service/artifact 和脚本调用回归。以后跨语言验收必须显式固定导入根目录、UTF-8 编码和 JSON 容器形状，不能假设 shell 管道会保留数组边界。

## 结构化澄清丢失能力目录中文标签

### 现象

开放式空间请求进入 `NEEDS_CLARIFICATION` 后，后端返回了能力 ID，但前端用于显示中文名称的 `suggested_capability_details` 为空；能力分类函数本身已经生成了目录详情，问题只在最终澄清对象中看不到。

### 根因

`classify_spatial_intent()` 返回了能力目录详情，但 `clarification_details()` 只复制了 `suggested_capabilities`、`missing` 和 `next_actions`，没有把目录详情继续传到 Runtime、result envelope 和 HTTP。前端因此只能尝试用 ID 兜底，形成了重复的能力标签映射风险。

### 处理与预防

M111 为澄清对象增加 `spatial-agent.clarification.v1`、有界的 `suggested_capability_details` 和 `matched_capability_details`，标签继续来自 CapabilityCatalog；Service、HTTP、result envelope 和计划预览均增加跨入口回归。以后结构化澄清新增字段必须检查“意图分类 -> Runtime 异常 -> result envelope/持久化 -> HTTP/Console”的完整链路，不能只在分类函数中增加字段。

## 公共 Runtime 的能力目录写死 GIS 数据集

### 现象

项目的 Runtime、Planner 和 ToolRegistry 接口看起来可以复用，但新增 Domain Pack 时发现 `agent/capability_catalog.py` 同时保存 `dem`、`land_use`、`roads`、`water`、GIS 能力和 GIS workflow 语义。非 GIS 领域如果直接复用该模块，会意外获得 GIS 能力目录，或者只能复制一套 Runtime。

### 根因

领域目录和通用编排契约缺少清晰的 seam。早期 GIS 只是唯一业务载体，因此把数据集映射、能力定义和模板放在公共模块中很方便；随着开放式 Agent 目标明确，这些实现细节变成了核心 Runtime 的隐式依赖。只移动常量而不移动 discovery/workflow context，仍会留下同样的耦合。

### 诊断

用一个不含 GIS 数据集的 fake Domain Pack 注入 `AgentRuntime`，检查 planner context 的 `domain_id`、`capability_discovery`、`capability_catalog` 和 `workflow_templates`。如果 context 仍出现 GIS 能力、GIS 模板或固定数据集名，说明只是增加了适配器外壳，并没有完成领域解耦。

### 修复

M112 新增 `DomainPack` seam，领域包负责 capability catalog、discovery 和 workflow context；GIS 实现迁入 `domains/gis`。公共 catalog 构造器改为接收能力定义、数据分组、工具映射、workflow templates、domain id 和 analysis-ready 能力集合；默认 GIS 与旧导入名保留兼容。新增非 GIS fake pack 和非 GIS catalog builder 回归，确认 Runtime 不再注入 GIS workflow context。

### 预防

以后新增领域不得直接把数据集名、能力 ID 或结果模板写入 `agent/runtime.py`、通用 context builder 或公共 HTTP 逻辑。至少要提供一个不含 GIS 术语的 Domain Pack/replay，并验证 RequestFacts、TaskPlan、ToolRegistry、result envelope、trace 和 artifact 的跨领域闭环。只把数据常量挪到新目录而不检查 discovery、workflow、result views 和 provenance，不能视为完成解耦。

## 非 GIS Domain Pack 的 planning evidence 缺少领域标识

### 现象

非 GIS Domain Pack 已经可以经过 Runtime 执行工具并生成 Service/artifact 结果，但 `result.planning` 没有 `domain_id`。前端或跨入口验收无法判断该计划由哪个领域能力包产生，只能从工具名称或结果类型反推领域。

### 根因

`domain_id` 已存在于 Domain discovery 和 CapabilityCatalog，但 `_build_plan_evidence()` 只记录了能力 ID、工具名和目录摘要，没有把领域边界投影到统一 planning evidence。该问题不是 GIS 数据错误，而是领域扩展信息在 Runtime 到 result envelope 的链路中丢失。

### 修复与预防

M113 将 `domain_id` 加入通用 planning evidence，优先读取 discovery，缺失时读取 capability catalog，未知领域使用 `unknown`；Runtime 不对具体领域值做分支判断。以后新增 Domain Pack 必须验证 domain id 从 discovery/catalog 贯穿 Runtime、Service、artifact 和 Contract Harness，不能只测试工具能否执行。

## Runtime 默认行为隐式绑定 GIS composer 与权限

### 现象

即使注入了非 GIS Domain Pack，Runtime 在调用方没有显式传入 `answer_composer` 或 `allowed_permissions` 时，仍会创建 GIS `AnswerComposer` 并使用 `spatial_data:read`。非 GIS 工具可能因此执行失败，或答案组合误走空间分支。

### 根因

早期 GIS 是唯一领域，Runtime 构造函数直接把 GIS composer 和空间读取权限作为默认值。M112 虽然把能力目录和 discovery 下沉了，但没有同步处理执行后的答案组合和安全默认值，造成领域解耦只完成了一半。

### 修复与预防

M114 增加 Domain Pack 的 composer/默认权限 seam；Runtime 优先使用领域包提供的实现，显式调用参数仍可覆盖，缺少旧 Domain Pack 方法时才使用 GIS 兼容 fallback。以后新增 Domain Pack 必须验证默认权限、工具执行和答案组合均不依赖 GIS；不要只验证 planner context 没有 GIS 字段。

## 新结果 registry 破坏旧自定义 Runtime 的兼容性

### 现象

M115 为让 Service 使用 Domain Pack 的 result registry，最初在所有 Service 结果路径直接调用 `runtime.result_registry()`。已有测试和扩展中的最小自定义 Runtime 没有该可选方法，异步几何证据回归在运行详情阶段出现 `AttributeError`。

### 根因

结果 registry 是新增的扩展 seam，但 Service 把它当成了旧 Runtime 必须实现的强制接口；这违反了 Planner、Backend、Domain Pack 可替换且向后兼容的边界。问题与空间几何无关，只在恢复/详情路径触发。

### 修复与预防

Service 现在通过有界的可选能力读取函数获取 registry；缺少该方法时将 `None` 交给 `build_result_contract()`，由兼容默认 registry 处理。以后扩展 Runtime/Domain Pack seam 时，必须至少用一个旧式最小 fake Runtime 覆盖同步、异步、重试、详情和 artifact 路径，不能只测试新实现。

## HTTP 能力目录绕过 Runtime 直接导入 GIS catalog

### 现象

Service 已支持注入 Text Domain Pack，但开发 HTTP `/capabilities` 和生产 FastAPI `/capabilities` 仍直接调用公共 GIS `capability_catalog()`。因此同一个应用的执行入口可以使用非 GIS Domain Pack，能力目录入口却返回 GIS 能力。

### 根因

能力目录最初被当作静态 GIS 配置，HTTP 模块直接导入函数；Domain Pack 引入后，目录实际已经是 Runtime 的领域状态（domain、backend、可用能力），但入口没有沿用 Service/Runtime seam。

### 修复与预防

M116 增加 `AgentRuntime.capability_catalog()` 和 `AgentService.capabilities()`，两个 HTTP 入口通过它读取实际 Domain Pack，并支持 planner/backend 参数；GIS 数据健康探针保留为独立的 `/capabilities/runtime` 兼容路径。以后新增 HTTP 能力入口必须使用 Service/Runtime，不能直接导入任一领域的 catalog 常量。

## runtime snapshot 迁移时破坏旧 provider 与隔离测试边界

### 现象

将 `/capabilities/runtime` 从旧 GIS snapshot 函数迁移到 Service/Runtime 后，旧测试通过 patch 模块级 provider，且部分隔离 handler 故意没有 Service；如果直接删除旧函数名或强制调用 Service，会让兼容测试在业务执行前失败。

### 根因

旧函数同时承担了三种角色：GIS 数据健康实现、HTTP 入口 provider 和测试替身 seam。迁移时没有区分“正常请求的 Runtime 路径”和“无 Service 的隔离 harness 路径”，导致基础设施兼容边界被误当成业务逻辑。

### 修复与预防

M118 保留有界的旧 provider 包装：正常 HTTP 请求使用 Service/Runtime，`service=None` 的隔离 handler 才使用旧 provider；GIS 数据证据由 `GisDomainPack.runtime_evidence()` 注入。以后迁移入口时必须分别测试正常 Service、无 Service 隔离、旧 patch seam 和真实生产依赖，不能只看单一路由返回值。

## Provenance 只总结 GIS 字段，非 GIS 工具缺少通用证据

### 现象

文本 Domain Pack 可以执行并导出 artifact，但 provenance 的 `result_summary` 原先只提取行政区、CRS、栅格统计等 GIS 字段，文本工具的 `word_count`、`char_count` 等安全计数不会进入审计证据；provenance 也没有标明结果属于哪个 Domain。

### 根因

provenance 在 GIS-only 阶段通过固定字段白名单快速实现，随着 Domain Pack 扩展，该白名单成为隐式领域耦合。直接复制所有结果字段又会泄漏原始文本、敏感参数或大 payload，因此不能用无界序列化解决。

### 修复与预防

M119 为 provenance 增加版本和 `domain_id`，并只自动提取 bounded numeric `*_count` 作为通用摘要；任意文本和原始 payload 仍不自动复制。以后新增领域应优先提供安全的 evidence projection，不能把完整工具结果塞进 provenance。

## 迁移领域 view builder 时容易误删公共对比视图依赖

### 现象

M122 将 `result_contract.py` 中的 GIS view builder 整段迁移到 `domains/gis/views.py` 后，GIS 和 Text 主路径可以正常导入，但公共的比较结果 view 仍调用 `_first_present`、`_view_metric` 等小函数；如果把这些函数和 GIS 实现一起删除，比较接口会在运行时出现 `NameError`。

### 根因

早期 GIS view builder 与通用 comparison view 共用同一文件和若干无类型归属的小工具。文件位置掩盖了真实依赖关系，按连续代码块迁移时容易把“通用 view primitive”误判为 GIS 实现。

### 修复与预防

M122 将 GIS builder 整体下沉后，在公共 `result_contract.py` 仅保留 comparison 所需的 `_first_present`、`_view_metric` 和几何范围校验等通用 primitive；GIS 领域 view 自己保留其内部的 row/metric helper。新增跨领域 view smoke 和全量回归，覆盖 GIS result、Text generic result 与 comparison result。以后迁移领域实现前应先用调用点反向检查依赖，将公共 primitive 与领域 builder 分开测试，不能依据文件连续区间直接删除。

## 前端用数据集关键词预判会阻断新增领域请求

### 现象

旧 Console 在发送请求前通过 `needsRaster` 正则识别 DEM、土地利用、坡度等 GIS 词汇，并在内存后端或本地 GIS 不可用时直接阻断请求。这个判断只覆盖已知 GIS 表达，新的 Domain Pack、同义表达或不需要栅格的开放式问题可能在到达 Planner/Runtime 前被错误拒绝。

### 根因

前端把数据依赖和后端可用性当成了页面本地规则，而不是由 Runtime 的能力目录、工具 schema 和数据健康门控决定。页面因此复制了领域语义，也可能与后端实际降级策略不一致。

### 修复与预防

M123 删除 `needsRaster`、`local_gis_backend` 和固定数据集词汇的发送前预判，仅保留空请求和通用模型配置检查；具体能力、数据依赖和降级说明由 Service/Runtime 返回结构化结果。以后前端不得依据领域关键词决定请求是否可执行；如需提前提示，应消费 `/capabilities` 或 result envelope 的通用 capability/degradation 字段。

## Domain Action 已接入但前端仍绕过通用 seam

### 现象

M124 后端已经提供 Domain-owned action catalog 和 `/actions/{action_id}`，但 Console 的三个比较按钮仍直接调用旧 comparison 路由。这样新增 Domain Pack 时，前端仍依赖 GIS 专用 URL，后端的通用 action seam 只是表面兼容层。

### 根因

旧 comparison 路由同时承担了 Service adapter 和页面调用契约；新增 action metadata 时只迁移了 HTTP 后端，却没有同步迁移前端的发现与 dispatch 流程。页面因而无法根据当前 Domain Pack 的 catalog 判断动作是否存在，也无法验证动作输入契约。

### 修复与预防

M124 让 Console 启动时读取 `/actions`，通过有界 catalog 校验动作已由当前 Domain Pack 声明，再统一 POST `/actions/{action_id}`；旧路由保留为兼容 wrapper。以后新增领域动作必须同时验证“Domain spec -> Runtime dispatch -> HTTP -> Console catalog/dispatch -> 结果 view/artifact”的链路，不能只增加一个后端 URL；动作执行也不能通过任意 Service 方法反射。

## 公共 Runtime 的数据预检规则泄漏 GIS 领域

### 现象

在 M125 审计中，`agent/runtime.py` 直接维护 DEM、土地利用、道路、水体和像元对齐工具的健康预检规则。即使 Planner、ToolRegistry 和 Domain Pack 已可替换，新的非 GIS 领域仍会被迫经过 GIS 语义的预检分支。

### 根因

早期 GIS 是唯一领域，数据依赖证据、网格关系和失败提示被放进 Runtime 的统一执行循环；后来增加 Domain Pack 时只迁移了 catalog、composer 和结果 registry，没有同步迁移执行前的数据策略。

### 修复与预防

M125.1 新增 `DomainPack.preflight_tool()` seam，将 GIS 实现移动到 `domains/gis/preflight.py`；Runtime 只计算 ToolRegistry 声明的通用依赖并委托领域策略。以后新增领域不得把数据集名、对齐关系或领域失败文本加入 `agent/runtime.py`；应通过 Domain-owned preflight/evidence provider 接入，并用非 GIS Domain Pack 负向测试确认无语义泄漏。

## Domain Action catalog 有 schema 但 dispatch 未校验输入

### 现象

M124 的 Action catalog 已返回 `required`、属性和结果类型，但 `/actions/{action_id}` 初始只检查 action 是否已声明，不校验缺失字段、未知字段或嵌套数组类型；错误只能在领域 Service adapter 内部偶然暴露。

### 根因

Action metadata 最初被当作前端发现信息，而 ToolRegistry 的 schema validator 没有被设计成可复用的公共输入契约；直接复用任意 Service 方法又会破坏显式 dispatch seam。

### 修复与预防

M125.1 新增有界 `validate_action_payload()`，在 Domain-owned dispatch 前校验声明的 JSON schema 子集，并增加缺失/未知字段回归。以后新增 Action 必须把 metadata、校验、错误分类、trace、artifact/recovery 一起作为一个契约验收，不能只验证 happy path。

## 迁移 GIS Composer 时公共兼容导入与实现归属分离

### 现象

GIS `AnswerComposer` 原本位于 `agent/answer_composer.py`，旧测试和扩展直接导入该路径；如果直接删除文件，旧 artifact/测试会导入失败；如果只在 `domains/gis` 增加一个新包装，实际实现仍然属于公共层。

### 根因

早期 GIS 是唯一领域，答案组合实现和 Runtime 公共模块没有清晰的物理归属；后续 Domain Pack 迁移只改变了构造入口，没有同时处理旧导入路径和实现位置。

### 修复与预防

M125.2 将实现迁移到 `domains/gis/composer.py`，公共旧路径仅作为显式兼容 shim；新增归属测试确认 shim 不再定义 Composer。以后迁移领域实现要同时检查物理归属、旧导入、artifact/recovery 和跨领域默认构造，不能只修改调用方。

## 领域证据迁移时 HTTP 入口容易绕过 Domain Pack

### 现象

M126 将 runtime capability 与 release evidence 接入 Domain Pack 后，如果 HTTP 入口继续直接调用 `agent.runtime_capabilities` 或 `agent.release_evidence`，Text 等非 GIS Domain Pack 会在能力快照之外意外获得 GIS 数据状态；动作入口也可能只返回业务 payload，无法和普通运行共享 trace、result 和恢复证据。

### 根因

旧 provider 同时承担了 GIS 实现、脚本入口和测试替身三种角色。迁移时若只修改 Runtime 而不检查 Service、开发 HTTP、生产 FastAPI 和 artifact 读取路径，公共入口仍会绕过新的 seam。动作则没有天然的 `AgentRunResult`，直接复用普通运行对象会把领域动作伪装成 Planner step，或者复制另一套结果契约。

### 修复与预防

M126 增加 Domain-owned `release_evidence` seam；正常 Service/Runtime 请求使用当前 Domain Pack，旧 provider 只保留给明确的兼容/隔离路径。Text Domain Pack 返回 `not_applicable`，不会继承 GIS 数据语义。动作使用独立但共享结果契约的 Adapter：生成有界 `spatial-agent.action-execution.v1`、trace、result envelope 和 action artifact，并通过 `/action-executions/{id}` 只读恢复，不重新 dispatch。以后迁移领域证据必须同时检查“Domain Pack -> Runtime -> Service -> 两个 HTTP 入口 -> artifact/recovery -> Console”，不能只验证一个函数返回值。

## 新增非 GIS Action 会使旧的“空 action catalog”断言失效

### 现象

Text Domain Pack 原先作为无 GIS 领域 fixture，测试用例把它的 action catalog 固定断言为空。M126 为验证通用 Action 执行、错误和恢复链路增加 `text.summarize` 后，旧测试虽然没有 GIS 耦合，却仍然把 fixture 的历史状态当成接口契约，导致回归失败。

### 修复与预防

将测试意图改为断言 Text catalog 只包含 Text-owned action，且序列化内容不出现 GIS 语义；新增成功、输入校验失败、artifact 读取和 HTTP 恢复回归。以后非 GIS fixture 扩展能力时，测试应验证领域隔离和跨入口契约，不应把“当前没有任何能力”当作长期接口。

## Action 幂等需要同时绑定输入指纹与失败证据

### 现象

Action 增加幂等键后，如果只按键返回上一次结果，调用方可能用同一个键提交不同参数，却得到旧结果；失败 Action 也可能被误认为可以安全重试，从而再次调用领域逻辑。

### 根因

幂等键表达的是“同一逻辑请求”的身份，不是参数本身。Action 与普通 Run 不同，执行结果不在 Runtime 状态中长期保留；若不把规范化输入指纹、失败错误码和 artifact 一起持久化，服务重启后无法区分输入冲突，也无法证明失败没有被重复执行。

### 处理与预防

M127 使用 `action_id + canonical payload` 的 SHA-256 指纹绑定幂等键；相同指纹复用成功 artifact，不同指纹返回 `idempotency_conflict`，失败请求从原 artifact 重放结构化错误。以后新增幂等入口必须同时覆盖成功复用、输入冲突、失败重放和重启后读取，不能只测试两次 happy path。

## Action artifact 与普通 Run artifact 共用目录时必须区分入口

### 现象

Action 复用普通 artifact 根目录后，历史列表、运行指标和 JSON 下载入口如果只按 `*.json` 扫描，会把 Action 当成普通运行，或者把普通运行文件暴露为 Action artifact。

### 根因

物理目录相同并不代表契约相同：普通 Run 有 request/plan/steps，Action 有 action execution/result/recovery。仅靠文件名读取或前端猜测会造成跨入口字段错配。

### 处理与预防

M127 以 `spatial-agent.action-artifact.v1` 和 `action-` 文件名前缀建立 Action 专用列表、指标和 `/action-executions`/`/artifacts/actions` 入口；普通 `/runs` 与 `/artifacts/runs` 保持排除 Action 的行为。以后增加新 artifact 类型必须同时定义 schema discriminator、列表过滤、恢复接口和路径前缀。

## 脱敏模型回放扩展到非 GIS Domain 时不能复用 GIS 工具注册表

### 现象

原有模型回放 evaluator 默认使用 Demo GIS adapter。加入开放式文本请求后，如果只替换 fixture 而不替换 provider，回放会因工具不在注册表中失败，无法证明 Runtime 的跨领域可替换性。

### 根因

回放本身是 Runtime 的测试入口，工具注册表、Domain Pack、结果 registry 和答案组合必须与被评估领域一致；fixture 的 `domain` 只是数据，不能自动改变执行边界。

### 处理与预防

M127 为回放 fixture 增加有界 `domain` 标识，Text 使用 TextToolProvider/Text Domain Pack，GIS 继续使用 DemoSpatialAdapter；报告只输出领域、工具覆盖、结果类型、中文答案和脱敏 token/延迟指标。以后新增 Domain Pack 回放必须验证 provider、registry、composer 和 evidence 全链路一致，不得只改请求文本。

## HTTP artifact 动态根目录不能覆盖旧测试替身

### 现象

M127 为 Action artifact 增加了从 Service 的 `ArtifactStore` 自动解析根目录的逻辑，但旧 HTTP contract harness 会在 handler 子类上显式设置临时 `artifact_root`，普通 Run 下载因此被错误地导向 Service 默认目录。

### 根因

HTTP handler 同时支持生产默认目录、Service 注入目录和测试子类目录三种部署方式。只检查 Service 是否有 artifact store，无法判断调用方是否已经明确选择了更高优先级的测试/部署路径。

### 处理与预防

M127 规定显式的 handler 子类 `artifact_root` 优先；只有未覆盖默认属性时，Action/Run artifact 才跟随 Service store。以后给 HTTP 入口增加动态依赖解析时，必须先保留显式注入 seam，并用默认、注入、子类覆盖三种路径验证。

## CI 完整回归失败且无法读取远程失败堆栈时不应继续作为提交门禁

### 现象

GitHub Actions 的 smoke check 和 stage contract profile 连续通过，但每次 push 的完整离线 `unittest discover` 都失败，导致每次提交都发送失败邮件。GitHub job 元数据只能确认失败发生在完整回归步骤；当前令牌没有读取该仓库 Actions 日志所需的管理员权限，无法获取远程堆栈。本机只有 Python 3.14，无法直接用 CI 的 Python 3.11 复现；同一工作树的本地离线回归已通过。

### 根因

完整回归测试数量和环境敏感性已经超过日常提交门禁的稳定范围，但 workflow 仍把它与快速 smoke、阶段契约检查放在同一个必过 job 中。这样一个无法在本机定位的远程环境差异，就会把所有 push 标记为失败并持续触发通知；同时也没有区分“日常稳定门禁”和“阶段性完整验收”。

### 修复与预防

将 push/PR 的 CI 门禁收敛为 smoke check 和 `stage` profile；完整离线回归保留在同一 workflow 的 `workflow_dispatch` 手动入口，仅在明确需要时运行。以后新增测试应先进入快速、确定性的阶段 profile；重型或环境敏感的全量回归必须有独立的手动/阶段验收入口，并在能读取失败日志或复现同版本环境后再重新提升为提交门禁，不能用持续失败的门禁掩盖未知环境问题。

## 新增通用执行投影时必须兼容没有执行身份的旧 Contract Harness fixture

### 现象

M128 为 Run 与 Domain Action 增加统一 `spatial-agent.execution-record.v1` 投影，并让 Contract Harness 自动比较执行状态。旧的结果契约 fixture 只包含 result envelope，没有 `run_id` 或 `action_execution_id`；如果 Harness 无条件构造执行记录，历史契约检查会因缺少执行身份而直接报错，甚至让生产 acceptance checker 返回参数错误码。

### 根因

执行记录需要一个稳定身份，而旧 Harness 的最小 fixture 有意只验证结果 envelope，本身并不代表一次可恢复执行。把新能力当成所有历史 payload 的必填字段，会把“新增可选证据”错误升级成“旧契约失效”，破坏替换入口和 artifact 兼容。

### 修复与预防

`normalize_execution()` 只有在 payload 已有 Run/Action 身份或明确的 `execution_record` 时才生成执行投影；纯旧 result fixture 保持无 execution 字段。真实 Service/HTTP/artifact payload 则必须携带完整投影。以后扩展公共结果证据时，先区分“无身份的历史最小 fixture”和“真实执行记录”，为新增字段提供有界兼容路径，并同时验证 acceptance checker 的退出码。

## 公共 LLM Planner 不能持有 GIS 领域规划规则

### 现象

公共 `LLMPlanner._system_prompt()` 曾直接包含 DEM、土地利用、道路、水体、洪山区、建设筛选和空间总览等领域规则。即使 Runtime 已经选择了 Text Domain Pack，Planner 也天然携带 GIS 词汇，无法证明同一个 Planner 能被另一个领域安全复用。

### 根因

早期 GIS 是唯一业务领域，Planner prompt 同时承担了 JSON 输出协议、工具边界和领域知识三种职责。Domain Pack 后续虽然已经拥有请求事实、能力目录和工作流上下文 seam，但 Planner 仍绕过这些 seam 维护一份隐含的 GIS policy。

### 修复与预防

M129 增加 `DomainPack.planner_guidance()` 和版本化 `spatial-agent.planner-guidance.v1` 投影；公共 Planner 只保留 TaskPlan JSON、ToolRegistry、依赖引用和安全约束，GIS/Text 分别提供自己的工具语义、结果类型、规划、澄清和拒绝策略。guidance 进入模型前会有界规范化，并只渲染已注册工具的语义。以后新增领域规则必须进入 Domain-owned guidance 和对应负向隔离测试，不能继续追加到公共 `_system_prompt()`。

## 提交门禁不应重复运行完整阶段边界场景

### 现象

原来的 push/PR job 分别运行服务 smoke 和 `stage` profile。`stage` 本身还会运行 3 个阶段验收场景；通用问答和未注册空间能力虽然有独立契约价值，但每次提交都运行它们，与日常核心契约和服务 smoke 叠加后，反馈成本高于实际新增信号。完整离线回归也容易被误解为默认门禁的一部分。

### 根因

阶段验收与提交门禁没有明确分层：提交门禁需要快速发现共享契约和最复杂的组合流程，阶段收口才需要覆盖全部边界场景。把同一套 `stage` 作为每次 push 的默认门禁，会让低频边界检查挤占日常反馈时间。

### 修复与预防

新增 `ci` profile，保留 3 个 quick 核心契约、服务 smoke 和 `stage-spatial-analysis` 一个代表性复杂编排场景；完整 `stage` 仍保留通用问答与未注册空间能力，阶段收口时显式运行。`evaluate_global.py --case-ids` 只用于有界选择已存在的验收场景，不改变 Runtime 行为，也不删除历史测试。以后新增测试先判断它属于提交门禁、阶段验收还是环境专项，避免把所有测试都接入默认 push/PR 流程。

## 领域请求理解已接入但 Planner 仍可能重复抽取事实

### 现象

Runtime 已经通过 Domain Pack 抽取 `RequestFacts` 并生成 capability discovery，但 Rule Planner 过去会再次直接调用公共 `parse_spatial_request()`。这样领域自有的请求理解结果只用于上下文和证据，计划生成仍可能绕过它；同时公共 `agent/` 中的路由、目录和 GIS 解析实现会让新增领域继承兼容规则。

### 根因

早期 GIS 只有一个领域，解析器、路由器和 Rule Planner 可以共享同一套默认实现。引入 Domain Pack 后只增加了 Runtime seam，没有同时迁移实现归属，也没有规定 Planner 优先消费 Runtime 已确认的事实。

### 修复与预防

新增版本化 `request-understanding-guidance` projection，由各 Domain Pack 提供并进入 Context/plan evidence；普通 Rule Planner 请求优先消费 Runtime Context 中的 `RequestFacts`，直连调用和带结构化 workflow 的请求使用有界兼容解析 fallback（workflow hint 可能引入领域约束词汇）。GIS 请求解析实现、GIS 路由和路由信号分别移入 `domains/gis`，公共模块只保留领域无关 value objects 和惰性旧导入 facade；Contract Harness 同步比较新的请求理解证据。以后新增领域应实现自己的 facts extractor、discovery guidance 和 catalog，不得向公共 `agent/` 追加领域词汇。

## Domain Planner seam 接入后仍需区分选择归属与实现归属

### 现象

M131 已让 Runtime factory 通过 `DomainPack.rule_planner()` 选择确定性 Planner，但 GIS Planner 的具体构建策略和固定回答暂时仍位于公共兼容实现。若只验证“factory 返回了一个 Planner”，容易误以为公共 `agent/` 已经完成领域解耦。

### 根因

Planner 的选择 seam 和 Planner 的实现归属是两个不同问题：先建立替换契约可以降低迁移风险，但旧直连测试、Rule Planner builder 和默认回答仍可能把 GIS 规则留在公共模块。

### 修复与预防

M131 明确保留有界旧 `RuleBasedPlanner()` facade，同时把正常 Runtime factory/Text Runtime 切换到 Domain-owned Planner；阶段证据分别检查“选择来自 Domain Pack”和“实现是否已物理下沉”。后续物理迁移完成前，不宣称公共 Planner 已完全通用；新增领域必须提供自己的 Planner adapter、TaskPlan 回归和跨入口证据，不能只复用 GIS fallback。

## 测试 profile 叠加导致阶段验证重复

### 现象

项目已经把测试分成 `quick`、`ci`、`stage`、`full-stage`、GIS、live 和 Docker profile，但 `stage` 仍嵌套 `quick`，`full-stage` 又嵌套 `quick` 与 service smoke。这样同一批工作流契约和服务启动检查会在一次阶段验收中重复执行；复杂空间运行也同时出现在 quick 与 CI 代表场景中，增加耗时却没有增加等量信号。

### 根因

profile 最初按“逐层叠加保护”设计，没有区分“独立门禁可单独运行”和“上层 profile 组合所有下层命令”。阶段验收、提交门禁和发布前全量评测的职责边界因此发生重叠。

### 修复与预防

M131 将 `quick` 收敛为工作流编译与 Domain Planner 选择两个核心 tripwire；`ci` 保留 quick、service smoke 和一个复杂空间代表场景；`stage` 独立运行 3 个离线阶段场景；`full-stage` 独立运行完整全局离线评测/模型回放。历史测试和专项 profile 不删除，只通过风险明确选择入口。以后新增测试先归类为日常契约、阶段场景、发布全量或环境专项，避免默认 profile 互相嵌套造成重复运行。

## 领域实现物理迁移时兼容 facade 不能反向成为真实归属

### 现象

M132 将 GIS Rule Planner 从公共层迁移到 `domains/gis` 时，如果只在 Domain Pack 增加一个包装方法、仍让包装方法导入公共实现，运行结果虽然不变，但代码归属并未改变；如果 facade 顶层导入 Domain 实现，又可能触发 Domain catalog、request parser 和 planner 之间的循环导入。

### 根因

历史兼容导入路径同时被旧测试、CLI 和第三方调用使用，迁移时容易只改变选择入口而不移动实现；Domain Pack 又会被能力目录惰性加载，公共模块不能假设 Domain 包已经完成初始化。

### 修复与预防

M132 将 GIS Planner/Composer 的策略与 builder 代码物理放在 `domains/gis`，公共模块只保留惰性委托 facade；Domain Pack 也惰性构造 Domain-owned Planner。归属测试同时检查实现模块路径和 facade delegate，避免“能运行”被误认为“已解耦”；以后迁移领域实现必须同时验证物理归属、旧导入、惰性加载和跨入口结果契约。

## 动态模块属性不能替代模块内部的全局变量定义

### 现象

静态检查发现 `agent/capability_catalog.py` 通过模块级 `__getattr__` 暴露旧的 `DATASET_GROUPS` 兼容属性，但同一模块内部函数直接读取 `DATASET_GROUPS`。模块级 `__getattr__` 只服务外部属性访问，不会为模块内部的全局名称查找提供兜底；对应路径会触发 `NameError`。同一轮检查还发现 Runtime 使用了未导入的 `List`。

### 根因

兼容导出和内部实现共用了一个历史名称，迁移到惰性 GIS contract 后只保留了外部 facade，没有把内部读取改成显式的 lazy provider；静态检查此前未纳入稳定门禁，所以问题没有在代码合并时暴露。

### 修复与预防

清理阶段将内部读取改为 `_default_gis_contract()` 的显式结果，并补齐 `List` 类型导入；同时安装并运行 Pyflakes、Ruff（F401/F821/F841）和 Vulture。以后模块级动态导出只能作为外部兼容 API，内部逻辑必须调用明确的 provider；静态检查应作为开发/阶段检查的一部分，且要区分有意 re-export 与真正无效导入。

## 静态死代码报告必须经过相对导入和动态入口复核

### 现象

Vulture 会将 Domain Pack 的惰性 provider、结果 registry 的公共查询方法、兼容 alias、CLI 脚本以及通过 `dataclasses.asdict()` 输出的字段报告为低置信度未使用。简单按报告删除，可能破坏 HTTP/PowerShell 入口、旧导入或序列化契约。相反，`ServiceState` 的部分旧操作方法和 `AgentService._ensure_memory_session()` 在仓库内确实没有任何调用，属于可清理的历史残留。

### 根因

静态工具主要根据 Python 语法树和直接调用判断使用情况，无法完整理解相对导入、模块级 `__getattr__`、字符串路由、子类属性覆盖、脚本直接执行和反射序列化。把“无直接调用”与“无入口”混为一谈，会在清理时误删公共边界。

### 修复与预防

清理前先解析相对导入得到模块调用图，再搜索 README、API 文档、workflow、PowerShell、HTTP 路由、artifact/recovery 和 profile 入口；只有同时满足无入口、无契约、无文档引用且有专项回归替代，才删除。M132.1 只删除了确认无调用的内部 state/session/job 方法和测试替身字段，并保留兼容、CLI、registry 与反射字段。以后对低置信度报告必须记录“保留/删除”的证据，不能直接使用 `vulture --min-confidence` 结果作为删除清单。

## 脱敏模型响应重复时要区分 canonical fixture 与自包含回放 suite

### 现象

测试 fixture 中曾同时存在独立的 M65 空间总览响应和 M67 模型 fixture 内的同一 `response`；二者规范化 JSON 完全一致。M127 领域回放 suite 也包含同一空间总览响应，但它位于带 `domain`、provider metrics、turns 和 expected 的自包含回放协议中。

### 根因

不同里程碑逐步增加了“直接运行 Runtime”“模型质量评测”和“跨领域回放”三类证据，早期通过复制 JSON 降低了各测试的读取复杂度，却没有区分 canonical 模型响应和自包含回放数据。

### 修复与预防

删除独立的 M65 重复文件，M65 Runtime/ToolRegistry 测试从 M67 canonical fixture 读取 `response`；保留 M127 内嵌副本，因为把它改成外部引用会削弱回放 suite 的独立可移植性。以后新增 fixture 先检查规范化 JSON 是否重复：同一测试协议复用 canonical response，跨入口/跨领域回放若必须自包含则保留并记录理由，不能机械合并所有相同 JSON。

## 验证命令必须以实际测试入口为准

### 现象

阶段恢复信息中使用了历史性的测试模块简称，直接执行时出现 `ModuleNotFoundError`；实际测试文件已经按更具体的契约名称拆分，例如 M127 使用 `test_m127_runtime_action_contract.py`，M81 profile 使用 `test_m81_test_profiles.py`。

### 根因

里程碑文档中的“相关回归”是范围描述，不等于 Python 模块名；长期演进后，测试文件可能被重命名或拆分，但手工复验命令没有同步更新。若只根据旧模块名执行，会把验证入口错误误判成代码回归。

### 修复与预防

复验前先用 `rg --files tests` 和测试类名确认实际入口，再运行 unittest；文档中的 profile 命令优先作为稳定入口，模块级命令只引用当前存在的文件。测试入口变更时同步更新恢复文档和阶段记录，区分“命令错误”与“测试失败”。

## 通用 Runtime Factory 不能直接创建 GIS 工具注册表

### 现象

通用 `agent.runtime_factory.build_runtime()` 虽然可以接收任意 `DomainPack`，但原实现始终在公共工厂中创建 GIS `ToolRegistry`，非 GIS Domain 只能通过独立的测试 Runtime 绕过这条路径；`domains.text.runtime.build_text_runtime()` 还忽略了 `planner_name`，因此 Text 的 LLM Planner 切换没有真正接入通用工厂。

### 根因

GIS 是最早的业务领域，工厂同时承担了后端选择、工具定义加载、权限默认值和 Planner 构造。引入 Domain Pack 后只迁移了目录、Planner 和结果证据 seam，没有把“工具提供者”和“领域默认权限”一起迁移，导致选择归属与实现归属不一致。

### 修复与预防

M133 增加有界的 `DomainPack.tool_provider(backend_name, root)` seam，GIS/Text 分别提供自己的 ToolProvider；通用 Factory 通过 `ToolRegistry.from_provider()` 接入选定领域，并从 Domain Pack 读取默认权限。旧 Domain Pack 没有该 seam 时保留明确的 GIS 兼容 fallback；Text Runtime 改为委托通用 Factory，因此 rule/openai 两种 Planner 经过同一 Runtime 链路。以后新增 Domain 必须同时验证 rule、LLM、ToolRegistry、权限、结果类型和跨入口恢复，不能只验证能力目录或测试替身。

## 共享 SQLite 或 artifact 根目录时必须按 Domain 隔离运行结果

### 现象

M134 引入受控 Domain Registry 后发现，SQLite 的 `agent_runs`、`async_jobs` 和普通 run artifact 原来只按 `run_id`、session 或文件名读取。如果 GIS 服务和 Text 服务共用同一个数据库或 artifact 目录，历史查询、异步恢复、metrics 或 artifact 详情可能返回另一个 Domain 的结果；同名 `run_id` 还可能被新 Domain 覆盖。

### 根因

Domain Pack 之前主要存在于 Runtime 内部，持久化层没有把 Domain 作为结果身份的一部分。服务边界也没有固定当前 Domain，导致“工具执行已经隔离”被误认为“缓存、恢复和历史也已经隔离”。

### 修复与预防

M134 为真实 `AgentRunResult`、预览、run artifact 和异步 payload 保存 `domain_id`；SQLite 的 run/history/async recovery/metrics 查询、artifact 的读取/列表/Action 幂等查询均按当前 Domain 过滤。旧记录缺失字段时按历史默认 GIS 兼容；同一 `run_id` 属于其他 Domain 时拒绝覆盖，并返回明确冲突错误。生产和开发 HTTP 服务通过 `SPATIAL_AGENT_DOMAIN` 选择注册表中的 Domain，CLI 使用同一注册表的 `--domain`，`/domains` 暴露有限目录。以后新增持久化或缓存入口必须同时回答：身份是否带 Domain、旧数据如何兼容、跨 Domain 读取是否有负向测试、恢复 worker 是否只接管本 Domain 任务。

## 异步提交不能为了生成运行快照而同步初始化 Runtime

### 现象

M135 为异步任务增加 Runtime Context 后，`run_async()` 在提交阶段调用完整 Runtime 的 context builder。该路径会初始化工具 provider 和本地 backend；当 Runtime 初始化较慢时，异步提交被阻塞，违反“先返回任务 ID、后台执行”的接口语义。

### 根因

Runtime Context 同时承担了两种职责：提交前的配置选择快照，以及执行时的真实 provider/工具证据。直接复用执行 Runtime 生成提交快照，虽然字段准确，却把慢初始化带进了 HTTP/Service 提交路径。

### 修复与预防

M135 增加 Domain-owned `tool_provider_info()` 轻量 seam，并由 Runtime Factory 提供不打开 backend 的 submission context snapshot；异步 worker 启动后再创建真实 Runtime，并将实际 context 与已持久化快照校验。配置漂移返回 `runtime_context_mismatch`，不静默使用新配置执行。以后新增异步快照字段时，必须分别验证提交延迟、worker 初始化、重启恢复和配置漂移；不能用完整 Runtime 初始化作为提交前的只读 metadata 查询。

## 聚合证据层不能假设上游输入已经完成脱敏

### 现象

M137 的 `deployment_evidence` 聚合器在正常结果路径中接收的是已经过 `result_contract` 白名单处理的 `model_evidence`，但最初仍直接复制传入的 mapping。若其他入口直接调用聚合器并传入模型原文、API key 或私有路径，这些字段就可能进入部署证据，违反 evidence projection 不保存敏感信息的边界。

### 根因

脱敏逻辑只放在上游结果封装函数中，聚合器被误认为“内部 helper”，没有被当作独立的持久化/导出边界。共享证据函数未来可能被 runtime capabilities、release evidence、artifact 或第三方 provider 直接调用，因此不能依赖调用顺序保证输入已经安全。

### 处理与预防

M137 让 `deployment_evidence` 自身按 schema、执行模式、provider/model 身份、错误分类、耗时、token usage 和 bounded fixture id 做白名单归一化；不复制 `raw_response`、凭据、私有路径或未知字段，并新增直接传入敏感字段的负向回归。以后每个跨入口 evidence、artifact 或导出聚合层都必须自包含地完成有界归一化，同时验证“正常上游输入”和“直接传入未清理输入”两条路径。

## 公共兼容 facade 不应继续承载领域 intent 策略

### 现象

领域解耦后，公共 `agent/spatial_intent.py` 仍直接保存 GIS 的空间词汇、能力提示和缺参判断。即使 Runtime 通过 Domain Pack 选择 Planner，公共模块仍会让新领域继承 GIS 的开放式澄清策略；同时 GIS Planner 通过公共模块导入领域实现，物理归属与选择归属不一致。

### 根因

早期 GIS 是唯一业务领域，intent、路由和澄清逻辑都放在公共层。后续迁移 Planner/Capability Catalog 时只迁移了主要实现，历史导入兼容路径没有同步变成惰性 facade，导致“兼容入口”反向成为实际策略归属。

### 处理与预防

M139 将实现移动到 `domains/gis/intent.py`，GIS Planner 直接从 Domain 模块导入；公共模块只通过惰性 import 保留旧函数名。`DomainPack.clarification_details()` 与 Runtime fallback 让当前领域决定澄清内容，Text Domain 明确返回中性策略。以后迁移领域代码必须同时检查实现物理路径、正常 Runtime 选择、旧导入兼容和非 GIS 负向隔离，不能只验证调用结果不变。

## 生产验收脚本不能默认信任 WindowsApps 的 Python alias

### 现象

Docker 容器 healthy，真实 API 可用，但直接执行 `scripts/production_acceptance.ps1` 时，`sync/artifact` Contract Harness 失败且没有 Python 输出。宿主机的 `python` 实际解析到 WindowsApps Store alias；显式使用真实解释器后同一验收立即通过。

### 根因

脚本未配置 `SPATIAL_AGENT_PYTHON` 时直接调用字符串 `python`。WindowsApps alias 在部分主机上静默退出，导致 `$LASTEXITCODE` 非零但错误看起来像 Harness 或 API payload 不一致。

### 修复与预防

M140 增加 `Resolve-ContractHarnessPython`：优先显式解释器，再枚举可运行的 `python.exe`，跳过 WindowsApps alias 并执行短探针；Harness 失败时报告解释器路径、退出码和有界错误文本。以后跨语言验收入口不能假设 PATH 中第一个 `python` 可用，也不能输出密钥或模型原文。

## Compose 的 env_file 不能替代宿主机 volume 插值

### 现象

M140 用当前工作树执行不带 `--env-file` 的 Compose 重建后，容器虽然 healthy，但 `/capabilities/runtime` 返回 500，日志为 `admin_areas dataset has no files`；容器 `/data` 为空，挂载源是仓库默认 `./data`，不是 `.env.production` 的真实 GIS 数据目录。

### 根因

Compose 的 `env_file` 只向容器注入变量，不参与 Compose 文件自身的宿主机路径插值。`${SPATIAL_AGENT_HOST_DATASET_ROOT:-./data}` 在没有进程环境或显式 `--env-file` 时会回退到空目录。

### 修复与预防

生产重建使用 `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --force-recreate`，并检查 `docker inspect` 的 `/data` source、容器文件和 runtime health。以后不能只看容器 healthy；必须验证 Compose 展开、文件可见性和数据能力快照。

## 真实模型的多工具计划仍必须通过严格 DAG 和工具契约

### 现象

M140 live smoke 中，约束建设案例完成；空间总览案例的 provider 请求成功，但模型计划多生成了一个重复 `range_query`，并带有未声明依赖引用。Runtime 将其分类为 `tool_validation` 并拒绝执行；脱敏报告显示 provider error 为 `none`。

### 根因

模型能够理解任务并覆盖预期工具，但没有稳定遵守复杂总览计划的固定节点、唯一步骤和依赖声明。结果类型正确不能替代 TaskPlan schema、DAG 和 ToolRegistry 校验。

### 处理与预防

当前保留严格校验，不为 live smoke 放宽重复步骤、未知引用或工具白名单；只记录案例状态、错误分类、token/延迟等脱敏指标。下一阶段从全局 Agent 角度增强 capability-guided plan repair/retry 与结构化模型输出约束，且所有修复仍须经过同一 schema、DAG 和 ToolRegistry。

## 生产 JSON 未声明 UTF-8 会造成跨语言契约假失败

### 现象

Docker 容器健康、真实 GIS 数据可读，Python 侧直接比较 sync 与 artifact 结果一致，但 `scripts/production_acceptance.ps1` 的 sync/artifact Contract Harness 报告 `answer`、`request_facts.admin_name` 和 `result_title` 不一致。临时脱敏观测显示同步 HTTP 响应中的中文变成了乱码，而 artifact 文件中的中文正常。

### 根因

生产 FastAPI 路由返回默认 `JSONResponse` 时，响应头只有 `application/json`，没有声明 `charset=utf-8`。同步响应包含未转义的 UTF-8 中文，PowerShell 客户端按系统默认编码解码；artifact 使用 `ensure_ascii=True` 保存，只有 ASCII 转义序列，因此没有触发同一问题。实际结果并未发生变化，失败发生在跨语言传输边界。

### 处理与预防

生产 API 增加 `UTF8JSONResponse`，作为 FastAPI 默认 response class，并在 HTTP 异常处理器中显式使用；回归测试验证默认响应契约，Docker acceptance 进一步检查实际 `Content-Type: application/json; charset=utf-8` 并通过 sync/artifact harness。以后跨语言 HTTP acceptance 必须同时验证 payload 语义和 Content-Type/charset，不能把客户端乱码误判为 Runtime、数据或 artifact 一致性问题；临时诊断日志只能使用有标签的脱敏字段并在修复后删除。

## unittest 平铺 discovery 会绕过精简测试包

### 现象

仓库已经有 compact active suite，但执行 `python -m unittest discover -s tests` 仍会加载 133 个历史测试文件和 700 多个方法，导致开发者误以为精简没有生效。改成 `discover -s tests -t .` 后只运行 4 个 active gate 测试。

### 根因

当 `tests` 没有作为顶层 package 被发现时，unittest 会把 `tests` 当作平铺搜索目录，不调用 `tests/__init__.py` 的 `load_tests`。因此仅增加 package hook 不足，命令还必须显式指定仓库根目录为 top-level。

### 处理与预防

新增 `tests/__init__.py` 的 active module allowlist，并统一将 README、CI、smoke 和测试策略中的 discovery 命令改为 `python -m unittest discover -s tests -t . -v`。历史里程碑测试不删除，仍可通过 `python -m unittest tests.test_m80_replanning -v` 显式诊断；以后不要在默认脚本中使用没有 `-t .` 的平铺 discovery，也不要把完整历史矩阵塞回 quick/ci。

## 动态 unittest Handler 类体不能直接捕获同名局部变量

### 现象

为了在 compact gate 中复用一个隔离的 HTTP 服务，测试在方法内部定义 `TestHandler`，并直接写 `service = service`。运行时类体右侧名称不会按普通闭包规则解析同名方法局部变量，触发 `NameError`，容易被误判为 HTTP 服务初始化失败。

### 根因

Python 类体有自己的命名空间；类属性赋值左侧的同名绑定会遮蔽右侧名称的预期解析，不能把它当作嵌套函数闭包使用。

### 处理与预防

先将外层对象绑定为不同名称（例如 `handler_service = service`），再在类体中写 `service = handler_service`。动态测试 Handler 应保持隔离端口、显式关闭 server 和 executor，并优先纳入现有 compact 测试而不是新增一组重复 HTTP 测试。

## 宿主 Chrome CDP 不可用时不能伪造动态前端通过

### 现象

M144 尝试用隔离的无头 Chrome 运行 Console smoke；Chrome 进程存在，但以独立 profile 启动后没有监听 `127.0.0.1:9222`，因此动态 smoke 无法执行。与此同时，当前 Docker API 和前端静态契约均正常。

### 根因

浏览器 CDP 是宿主进程和端口级外部环境，不属于 Python Runtime 或 Docker 容器内的 API 契约。若只看到页面文件和 API healthy 就宣称浏览器通过，会把静态/后端证据误当成真实 DOM 行为证据。

### 处理与预防

将动态浏览器结果明确分类为“未执行/环境不可用”，保留 Console 静态契约、Node smoke 脚本语法检查和 Docker/API acceptance 作为独立证据；CDP 恢复后再运行 `scripts/console_*_smoke.js`。任何阶段文档不得用这些替代证据宣称动态浏览器 smoke 通过。

## 真实 GIS 冷启动超过过短的 HTTP 验收超时

### 现象

Docker 容器已经 healthy，但生产 acceptance 的第一个 `/capabilities/runtime?max_files=1` 请求超过 5 秒，PowerShell 报请求超时；随后同一路由正常返回 200，容易被误判为 GIS 依赖、Docker 或 Runtime 失败。

### 根因

生产服务首次生成 runtime capability snapshot 时会加载真实 GIS provider，并检查挂载数据、Rasterio/GDAL/PROJ 和 manifest。当前容器实测冷启动约 8 秒；readiness healthy 只代表服务可接收请求，不代表第一次重量级 capability 快照已经完成。固定 5 秒 GET 预算过短。

### 处理与预防

`production_acceptance.ps1` 将只读 GET 超时提高到 30 秒，仍保留有界等待；POST 请求继续使用 10 秒。以后遇到 acceptance 超时，先区分冷启动耗时、HTTP 路由错误和容器日志，再决定是否修复业务代码；不能因为一次短超时就放宽真实数据或工具契约。

## run artifact 缺少版本和文件名边界会影响迁移与恢复安全

### 现象

旧 run artifact 没有独立的 artifact schema 字段，服务只能依赖结果 envelope 的版本猜测格式；同时如果 recovery 直接把外部 `run_id` 拼接为文件名，斜杠或反斜杠可能让读取边界脱离 artifact 根目录。未知未来格式还可能被误当成当前格式。

### 根因

早期 artifact 主要服务于 demo 恢复，写入路径默认使用 Runtime 生成的 UUID，因而没有像 Domain Action 一样集中校验 run id，也没有单独的 artifact migration contract。随着 HTTP/SQLite/artifact/Console 多入口共用恢复逻辑，这个隐含前提不再可靠。

### 处理与预防

新增 `spatial-agent.run-artifact.v1`：新文件显式写版本；缺失版本的历史文件保持兼容；未知版本拒绝读取。`ArtifactStore` 对 run artifact 的写入和读取统一拒绝路径分隔符、`.`、`..` 和超长 run id，并继续按 Domain 过滤 recovery/list/read。以后新增 artifact 字段或版本时必须补当前/legacy/unknown 三类专项，而不能只测试新写入文件。

## HTTP artifact 下载绕过 Domain 过滤

### 现象

内部 `ArtifactStore.read_run/read_action` 已按 Domain 过滤，但开发 HTTP 和生产 FastAPI 的 artifact 下载只按文件名、后缀和目录判断。已知文件名时，Text 服务可以直接读取 GIS 的 run、action 或 GeoJSON artifact。

### 根因

HTTP 文件下载被当作静态文件服务，没有复用业务层的 Domain 身份；GeoJSON 旧格式又可能没有直接保存 Domain 字段，导致“路径安全”被误当成“领域隔离”。

### 处理与预防

新增有界 artifact access seam：校验文件名、类型、前缀、JSON 结构和 Domain；旧 GeoJSON 缺少 Domain 时只从同名 run artifact 读取元数据，无法绑定时按历史 GIS 默认。开发和生产入口共用该规则，并补 run/action/GeoJSON 的跨 Domain 负向测试。以后任何 artifact 下载、预览或导出入口都必须回答：当前 Domain 如何确定、旧文件如何兼容、跨 Domain 是否返回 404。

## 异步自定义 Runtime 的 Context 快照使用错误缓存 key

### 现象

Docker offline replay 的同步调用成功，但 HTTP async 提交在 worker 很快完成时返回 500，错误为 replay 工厂收到 `rule` 而不是 `openai`。慢一点轮询时又可能表现为 run detail 连接被关闭。

### 根因

`ServiceState` 用 `(planner, backend)` tuple 缓存 Runtime；`AgentService._submission_runtime_context()` 却使用 `"planner:backend"` 字符串查找，导致自定义 Runtime 的提交快照为空。async 观测随后按默认 `rule/memory` 重建 Runtime，绕过了原始 planner 选择。

### 处理与预防

改用 tuple key，并让 `get_run()` 在 URL 未提供 planner/backend 时从持久化 Runtime Context 或 async payload 推断实际选择。新增 Docker replay 红测覆盖快速 worker、HTTP async、轮询和重启恢复。以后新增 Runtime cache 或持久化快照字段时，必须同时验证 rule/LLM、memory/local、同步/异步和无 query run detail，不能只验证首次提交返回 run_id。

## Async artifact evidence 的首次轮询与恢复状态不一致

### 现象

真实 GIS Docker replay 中，首次 async 轮询的 evidence 一度显示 artifact 不可用，而服务重启后从 artifact 恢复显示可用；另一个环境中 GIS 结果因数据质量而显示 `degraded`，旧测试却硬编码 `success`。

### 根因

SQLite run snapshot 与最终 artifact 写入存在短暂时序差异，状态快照可能没有 `artifact_ref`，但 artifact 文件已经存在。测试还把真实 GIS 数据降级误当成失败，忽略了项目对 `degraded` 的合法契约。

### 处理与预防

async evidence 生成时在同一 Domain 的 ArtifactStore 中做有界 fallback，只取安全 artifact basename；artifact-only recovery 与首次轮询使用同一投影。Docker replay 允许 `success/degraded`，但要求 degraded 有非空降级状态且重启后保持一致。以后真实数据验收必须区分 `failed`、`unavailable` 和合法 `degraded`，不能为追求绿色测试放宽数据门控或硬编码 success。

## 嵌套结果 schema 分散校验会让未来 artifact 泄漏到恢复和前端

### 现象

result envelope、workspace、views、view/panel 和 async evidence 原先由不同入口分别读取。旧 artifact 缺少版本时可以兼容，但未知的嵌套版本可能被某个入口当作当前结构继续透传，导致恢复结果、HTTP artifact 下载和 Console 对同一份数据产生不同解释。

### 根因

版本常量虽然存在，迁移策略却没有统一的深层边界；artifact recovery、async polling 和前端 renderer 各自只检查了最外层或部分字段。这样会把“旧数据兼容”和“未来数据安全拒绝”混为一谈。

### 处理与预防

M149 增加无领域依赖的 `agent/nested_schema.py` 作为统一迁移/校验 seam：缺失版本只执行有界 legacy migration，未知版本抛出带 `reason_code` 的 `NestedSchemaError`。artifact/HTTP/async recovery 使用 `unavailable` fallback 或安全拒绝，Console 使用同样版本表做前端空态保护；replay/live 评测和生产验收复用对应的脱敏证据。以后新增嵌套结果字段必须同时补当前、legacy、unknown 三类测试，并验证同步、异步、artifact、HTTP 和前端的解释一致性。

## M150：Contract Harness 漏掉 artifact 顶层异步证据

### 现象

当前 Docker 生产 acceptance 在 `async/artifact` Contract Harness 处失败，差异只有 `$.async_result_evidence`。异步运行结果本身和 artifact 都已成功，repair lineage、视图和部署证据也一致。

### 根因

在线终态通过 `async_observability.result_evidence` 暴露有界异步证据；run artifact 为支持 artifact-only recovery，将同一投影持久化在顶层 `async_result_evidence`。Contract Harness 只读取在线 observation 和兼容的 `result_evidence` 路径，没有读取 artifact 的持久化路径，因此把同一份证据误判为缺失。

### 处理与预防

`evaluation/contract_harness.py` 的异步证据投影现在按顺序读取在线 observation、兼容顶层 `result_evidence` 和 artifact 顶层 `async_result_evidence`。新增 M150 HTTP/artifact 回归先验证该问题为红灯，再验证修复后同步/异步 artifact 等价。以后新增持久化证据字段时，必须列出在线、artifact、recovery 三种来源并让 Harness 共用同一投影，不能只测试单一路径。

## M150：FastAPI TestClient 的可选 httpx2 依赖不能冒充生产失败

### 现象

Docker 生产镜像中 FastAPI 和 Uvicorn 均可用，真实 `/health`、同步、异步和 artifact acceptance 全部通过；但运行 M150 Python 专项时，`fastapi.testclient` 因 Starlette 缺少 `httpx2` 抛出 `RuntimeError`，导致测试进程失败。

### 根因

`httpx2` 是 TestClient 的测试依赖，不是 Uvicorn 生产 HTTP 入口的必要依赖。测试原先只捕获 `ModuleNotFoundError`，没有把 TestClient 导入阶段对可选依赖的 RuntimeError 归类为环境跳过。

### 处理与预防

M150 测试现在同时处理模块缺失和 TestClient 导入 RuntimeError，并以明确原因跳过可选 FastAPI TestClient 矩阵；生产镜像不为测试工具强行增加依赖，实际生产路径继续由 Uvicorn acceptance 覆盖。以后遇到可选测试客户端缺失，必须区分“生产入口不可用”和“测试适配器不可用”，不能把后者改写成业务失败，也不能静默跳过而不说明原因。

## M151：用户批准后不能重新生成计划

### 现象

计划确认功能如果只在批准请求中再次调用 Planner，即使 plan fingerprint 仍然存在，也可能因真实模型具有随机性而得到不同的步骤、参数或依赖；这会让用户批准的内容与实际执行内容不一致。

### 根因

早期 `preview`/`run` 链路把 fingerprint 当作比较字段，而没有把经过校验的 TaskPlan 作为可恢复执行快照。对于 live Planner，重新规划并不能保证与预览计划等价。

### 处理与预防

M151 在计划校验后持久化完整运行快照和 `DecisionRecord`，批准时通过 CAS 消费决策，并从原运行快照执行，不重新调用 Planner；执行前再次检查 Domain、run_id、decision version 和 fingerprint。以后所有需要用户确认的 Agent action 都必须明确保存“用户批准的对象”，不能只保存请求文本或比较指纹；并补充同步、异步、SQLite 重启和重复 resolve 的测试。

## M152：artifact 只保存摘要会导致批准后无法恢复原计划

### 现象

待确认运行的 SQLite 快照已经保存完整 TaskPlan，但无 SQLite 的 artifact-only 服务只能读到旧 artifact 的计划摘要和步骤结果，找不到可执行的参数与依赖，因此无法在重启后批准并继续原计划。

### 根因

artifact 最初主要用于展示和恢复结果，`plan` 只保存 goal/output/assumptions，`steps` 也只保存结果摘要。用户确认要求恢复“被批准的对象”，不能只恢复结果展示字段。

### 处理与预防

M152 在 artifact 中增加有界 decision record/evidence 和完整计划节点（工具、参数、依赖），并通过安全的 decision scan 找回记录；恢复后仍经过 Domain、fingerprint、version 和 ToolRegistry 边界。以后涉及继续执行的 artifact 必须同时验证“展示恢复”和“执行恢复”，对参数做深度、数量和字符串长度限制，不能把摘要 artifact 当作可执行快照。

## M153：用户决策状态不能替代运行全生命周期

### 现象

M151/M152 已有 `DecisionLifecycle`，但它只描述批准、拒绝和消费等持久化决策状态。若让 result、异步轮询、artifact 或 Console 直接拼接澄清、修复、重试、恢复和取消状态，就会出现同一运行在不同入口显示不同可操作动作的问题。

### 根因

用户决策记录和运行状态属于不同抽象：前者需要 SQLite/CAS/TTL 和可恢复写入，后者应该是对当前 bounded run payload 的只读解释。把两者合并会让纯展示逻辑依赖 DecisionStore，也会诱使入口自行推断状态、复制失败分类和重试计数。

### 处理与预防

M153 新增无 I/O、无领域依赖的 `agent/action_lifecycle.py`。`project_action_lifecycle()` 只接收运行或 Action 的有界 payload，统一投影 `planning`、`executing`、`awaiting_confirmation`、`clarification_required`、`repairable`、`recoverable`、`completed`、`rejected`、`cancelled` 和 `failed`，并只输出 allowlist 动作、原因码、尝试次数和修复/重试/恢复计数。result envelope、artifact、async evidence 和 Console 均消费 `spatial-agent.action-lifecycle.v1`；旧 async evidence 缺少该字段时按状态生成有界 fallback，未知版本不能静默透传。以后新增生命周期动作必须先扩展这个投影及其跨入口契约测试，不能在 HTTP、前端或 artifact adapter 中各自增加状态判断。
## M153：真实模型会重复生成已存在的工作流步骤

### 现象

在当前版本用真实模型、武汉 analysis-ready 数据和本地 GIS 后端运行 `live-short` 时，空间总览与约束建设两个案例都能返回正确的结果类型、中文答案和完整工具覆盖，但最终状态为 `FAILED`，错误分类为 `tool_gate`。模型生成的计划重复包含 `get_dataset_health_report`、`get_dataset_schema` 或业务分析工具，有限 repair 仍未收敛到模板允许的步骤集合。

### 根因

模型能够理解请求的能力目标，却没有严格遵守运行时上下文中已有 workflow/template 蓝图的步骤基数和唯一性约束。当前 Planner 只在模型输出后做校验，repair 反馈没有把“已存在的步骤不能重复、模板 blueprint 必须保持顺序和数量”收敛成足够强的修复协议。ToolRegistry 和数据门控正确拒绝了不可靠计划，因此不能把这次 live 结果算作成功。

### 处理与预防

M153 保持 ToolRegistry、workflow 和 DAG 门控不放宽，并将失败作为脱敏 `tool_gate`/repair evidence 保存；默认 CI 不引入 live 网络。后续阶段应从通用 Planner/Workflow seam 处理：给 repair 输入增加模板 blueprint 的有界结构摘要，分别验证重复工具、步骤数量、依赖和结果引用，并让 replay/live 使用同一计划质量契约。不能针对“空间总览”或“建设筛选”增加一次性去重分支，也不能静默删除模型步骤后继续执行。

## M154：宿主 Python 与 GIS conda/Docker 环境不一致会伪造 live 失败

### 现象

使用宿主 Python 3.14 运行 `live-short --live-backend local` 时，真实模型请求可以成功，计划也通过 blueprint 校验，但所有 GIS 数据健康状态显示 `unavailable`，错误包括 `rasterio is required`，工具随后被 `tool_gate` 拒绝。换到 `spatial-agent-gis` conda 环境后，建设筛选案例可以完成；最终重建 Docker GIS 环境后两个 live-short 案例均通过。

### 根因

宿主解释器与 GIS 依赖环境不是同一个运行时。`rasterio`、GDAL/PROJ 和 GeoPandas 不属于普通 Python 环境；模型、Runtime 和 ToolRegistry 的可用并不代表真实 GIS provider 已具备像元和矢量读取能力。

### 处理与预防

真实 GIS/live 验收必须使用 `spatial-agent-gis` 或包含 GIS 依赖的 Docker 镜像，并显式设置 `SPATIAL_AGENT_DATASET_CONFIG`。生产阶段优先使用 `docker compose --env-file .env.production -f docker-compose.prod.yml build`、`up -d --force-recreate` 和 production acceptance；先记录解释器/镜像、provider、数据配置和健康状态，再判断业务失败。以后不能用宿主 Python 缺少 Rasterio 的结果否定 Planner 或 GIS 代码，也不能用旧容器结果替代当前镜像证据。

## M154：真实模型会使用 schema 外的比较符别名

### 现象

在 Docker GIS live 中，模型生成的 `range_query` 计划结构、工具、依赖和结果类型都正确，但条件中的标准字段 `operator` 被输出为 `op`，或值被输出为符号 `=`。ToolRegistry 按正式 schema 拒绝该参数，错误分类为 `tool_validation`。

### 根因

结构化输出约束保证了大体 JSON 形状，但不同 OpenAI 兼容 provider 对嵌套条件字段的遵循程度不一致；模型理解了“等于”语义，却没有稳定使用项目定义的枚举词汇。放宽 Registry 或静默删字段会破坏执行边界。

### 处理与预防

M154 在 LLM Planner 边界增加有限 canonical normalization：仅对 `range_query` 的无歧义 `op` 别名和 `=、==、!=、>、>=、<、<=` 做标准化，未知值和冲突字段继续交给 schema/ToolRegistry 拒绝。补充离线别名回归和 Docker live 验收；以后类似兼容处理必须位于 Planner adapter、映射范围有 allowlist，且最终仍经过统一 schema/Registry，不能在 Runtime 或具体 GIS 工具中偷偷修正。

## M155：异步结果证据只投影视图会丢失计划质量

### 现象

同步结果和 artifact 已经包含 workflow blueprint 的计划质量，但异步轮询 evidence 只保留 workspace/views、降级状态和生命周期。前端或跨入口 Harness 只能知道视图是否可用，无法判断异步结果是否沿用了已校验的计划，也无法区分“无唯一蓝图”和“蓝图不匹配”。

### 根因

异步 evidence 最初被设计为轻量 renderer 选择器，计划来源与 repair lineage 被认为可以通过完整 `/runs/{id}` 另行读取。随着异步轮询、artifact-only recovery 和多入口一致性成为同一结果契约，这个假设会让轮询和完整结果产生不同的证据解释。

### 处理与预防

新增 `spatial-agent.plan-quality-evidence.v1`，并在异步 evidence 的 `planning.plan_quality` 中保留有界投影；Contract Harness、artifact recovery、replay/live 和 Console 统一消费该投影。没有唯一 workflow blueprint 时必须返回 `available=false` 和 `workflow_blueprint_unavailable`，不能根据 result type 猜模板。以后新增结果证据时，要同时检查同步 envelope、异步轮询、artifact-only recovery、历史兼容和前端 renderer，不能只在完整 run detail 中增加字段。

## M156：执行时间线在异步归一化时丢失空字段导致跨入口差异

### 现象

同步 result envelope 的 execution timeline 在事件中保留了值为 `null` 的可选字段，而异步 evidence 归一化只保留非空字段，导致 Contract Harness 比较同步与异步时间线时出现结构差异。实际业务状态没有变化，但跨入口证据无法直接等价。

### 根因

时间线首次实现时，构建器和归一化器对可选字段的输出策略不一致：一个直接写入 `None`，另一个按“安全字段”过滤。结构化证据契约比较的是 JSON 形状，因此不能把这种差异留给前端或 Harness 自行容忍。

### 处理与预防

时间线构建阶段不输出空可选字段，归一化阶段继续使用同一 allowlist；未知版本、缺失事件和旧 artifact 明确返回 unavailable。以后新增跨入口证据字段时，必须先定义 canonical JSON 形状，再同时验证构建、归一化、artifact recovery、async polling 和 Harness，不能只比较业务值。

## M157：时间线直接透传动作会绕过生命周期安全边界

### 现象

执行时间线为了让前端显示可操作动作，需要携带 `allowed_actions`。如果归一化器只检查字段类型而直接透传，手写 artifact 或伪造 async evidence 就可能把未被 Runtime 批准的动作显示给用户，造成前端状态与实际生命周期不一致。

### 根因

时间线是展示投影，不拥有动作策略；动作策略已经由 `ActionLifecycle` 统一维护。若在 timeline、HTTP 或 Console 各自维护动作名称，会产生重复的 allowlist 和跨入口漂移。

### 处理与预防

时间线构建与归一化统一复用 `ActionLifecycle` 的 allowlist，未知动作直接过滤；timeline 不负责执行动作，真正的批准、重试、恢复和工具调用仍由 Runtime、DecisionStore 与 ToolRegistry 处理。以后新增可操作状态必须先扩展生命周期契约和跨入口 Harness，不能在前端或 artifact adapter 中直接添加动作。

## M158：Evidence Registry 如果不限制引用类型会重新引入路径泄漏

### 现象

Evidence Registry 需要给前端和跨入口 Harness 提供证据定位。如果 Registry 直接接受任意 `file`、`http` 或宿主路径引用，虽然证据正文没有泄漏，前端仍可能通过索引暴露本机路径或访问不应公开的资源。

### 根因

Registry 是索引而不是证据内容，但早期设计容易把“可定位”误解为“保存真实地址”。同时 entry schema 如果不校验，未来版本可能被旧消费者静默解释。

### 处理与预防

Registry 只允许当前 allowlist 中的 schema 版本，引用限定为 `result` 或 `result.*` 的 JSON 路径；未知 entry schema、外部引用和未知 Registry 版本统一返回 unavailable。artifact、async、HTTP 和 Console 只消费该安全索引，不把它当作文件下载授权。以后新增 evidence entry 必须同时定义 schema allowlist、引用边界和未知版本回归。

## M159：异步 artifact 投影缺失 Registry 会造成历史/轮询证据分叉

### 现象

新写入的 run artifact 已经包含顶层 Evidence Registry，但旧版或异步 worker 在最终 evidence 投影写入前退出时，`async_result_evidence` 可能没有 Registry。历史列表、artifact-only recovery 和在线轮询因此可能显示不同的证据入口数量。

### 根因

Registry 首先接入了 result envelope 和 async projection；SQLite/history 使用的运行快照只保存 `AgentRunResult`，而该对象原先没有保存 Registry。artifact 顶层索引与 async 轻量投影也没有定义缺失场景下的有界 fallback。

### 处理与预防

M159 将 Registry 作为 `AgentRunResult` 的可选版本化字段保存到 SQLite/history，并在 artifact/history 列表统一规范化；artifact-only async recovery 在同一 Domain 内优先复用顶层 Registry。新增 `/runs/{id}/evidence` 和 artifact evidence 入口只返回 Registry 与安全 basename。以后新增跨入口 evidence 时，必须同时验证 result、SQLite history、async online、async artifact-only、HTTP 下载和 Console 导航；部分写入只能复用已存在的安全投影，不能根据 result type 猜测。

## M159：Domain 自定义 evidence 如果绕过公共 allowlist 会破坏可迁移性

### 现象

Domain Pack 需要把自己的 runtime/release 证据加入统一 Registry。如果直接把 Domain 自定义 schema 或文件路径塞入 Registry，旧 artifact、其他 Domain 和前端可能无法识别，甚至重新暴露本机路径。

### 根因

Evidence Registry 是公共可迁移索引，不应把 Domain 实现细节当作通用协议。自定义 entry 同时涉及 schema 版本、JSON 引用、状态和跨入口恢复；只在 Domain builder 中校验会让 artifact/HTTP/async 消费者各自解释。

### 处理与预防

M159 增加 `ResultContractRegistry.evidence_specs_for()` 作为 Domain-owned 声明 seam，但公共 Registry 只接受已知版本（当前领域证据使用 `spatial-agent.domain-evidence.v1`）和 `result`/`result.*` 引用；未知版本或外部引用被拒绝/降级。以后扩展 Domain evidence 必须补自定义 entry 的当前/未知 schema、跨 Domain、artifact 恢复和 Console 导航测试，并保持 Registry 不拥有 Runtime 动作策略。

## M160：Registry 有索引不代表证据入口完整

### 现象

M158/M159 的 Registry 可以完成版本和引用归一化，但旧 replay/Contract Harness 只要看到一个可解析 Registry 就会继续通过，无法发现核心入口缺失、重复、声明数量不一致或被截断。这样会让“可导航”被误认为“证据完整”。

### 根因

安全兼容读取与严格验收使用了同一个宽松投影：历史 artifact 需要有界降级，replay/live 则需要证明 `result`、计划质量、执行时间线、生命周期和重规划五类核心入口都存在。两种语义没有拆成独立 contract。

### 处理与预防

M160 增加领域无关 `spatial-agent.evidence-completeness.v1`，严格检查核心 entry、唯一性、entry_count、schema allowlist 和 JSON 引用；Contract Harness、脱敏 replay 和 live baseline 共用该投影。以后新增 Registry entry 必须区分“兼容读取”与“验收完整性”，不能仅以 `normalize` 成功作为通过条件。

## M160：真实模型完成工具执行但计划质量仍可能不匹配工作流蓝图

### 现象

当前 Docker GIS/live-short 中，空间总览案例通过 Registry 完整性与计划质量；约束建设筛选案例也完成了工具执行并返回正确结果类型，但真实模型额外生成了 `get_dataset_schema` 和 `range_query` 步骤，导致工具覆盖与 workflow blueprint 质量失败。该结果不能算作完整 live baseline 通过。

### 根因

开放式 LLM 运行没有显式 workflow selection 时，Runtime 会执行所有已注册且 schema 合法的工具；当前 capability catalog 记录了选中能力，但尚未把“唯一匹配工作流的 allowlist/蓝图”变成通用的执行前门控。因此 ToolRegistry 合法不等于计划符合该能力的最小蓝图。

### 处理与预防

M160 保持严格评测，不通过放宽 expected tools 或静默删除额外步骤来掩盖问题；同时在通用 Runtime 中增加可选的 Domain-owned `validate_plan` seam。GIS Domain 对唯一结果类型对应的工作流执行有界 allowlist/max-step 门控，违反时进入既有有限 repair；Text Domain 不实现该领域策略，公共 Runtime 不读取 GIS 名称。重建镜像后的 live-short 两个案例均通过。以后新增 Domain 计划策略必须通过同一可选 seam，并保留 repair lineage，不能增加某个区域或固定问句的专用去重分支。

## M160：Windows PowerShell/Chrome CDP 环境会阻塞动态浏览器验收

### 现象

`scripts/console_cdp_start.ps1` 用 Windows PowerShell 5.1 直接执行时，原无 BOM UTF-8 文件被误解码，产生脚本解析错误。改为 ASCII 机器输出并增加 `-Headless` 后，脚本可以解析，但当前机器上的 Chrome headless/普通进程仍在监听 CDP 前退出，动态 Console smoke 无法取得页面。

### 根因

Windows PowerShell 5.1 对无 BOM 脚本的默认编码与 PowerShell 7 不同；Chrome 进程退出则属于浏览器/显示环境边界，不是前端 HTTP 或 Runtime 失败。若把静态 Node smoke 或 Docker API acceptance 当成浏览器通过，会掩盖真实的动态验收缺口。

### 处理与预防

启动脚本的机器可见输出改为 ASCII，并支持显式 `-Headless`；动态浏览器证据继续单独记录为未验证，不能用静态契约替代。后续应先确认 Chrome 进程、独立 profile、CDP 端口和页面存活，再运行 Console smoke；浏览器不可用时只报告环境阻塞，不修改前端逻辑伪造通过。

## M161：宿主 Python alias 不能作为项目测试环境

### 现象

在宿主 PowerShell 执行 `python -m unittest` 或 `python scripts/test_profile.py` 时，命令解析到 `C:\Users\torch\AppData\Local\Microsoft\WindowsApps\python.exe` 占位 alias，进程无法启动。使用明确的宿主 Python 路径可以运行，但宿主环境不一定包含 Rasterio/GDAL 等 GIS 依赖。

### 根因

Windows 的 Python Store alias 与项目实际依赖环境不一致；普通宿主解释器即使能够运行离线 Runtime，也不能证明当前 Docker 生产镜像、真实 GIS 数据卷或容器内依赖可用。宿主测试还可能把“环境缺失”误判为代码回归。

### 处理与预防

从 M161 起，Python 单元测试、profile、compileall、GIS 回归和阶段验收统一在当前 Docker 镜像内执行，使用 `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --force-recreate` 重建后，通过 `docker exec ai-agent-spatial-agent-1 python ...` 运行。宿主 Python 只用于诊断 alias/依赖问题，不作为阶段通过证据；阶段记录必须区分容器结果、宿主诊断和 live/browser 环境状态。Docker 化不意味着恢复完整历史测试矩阵，仍按 quick、stage、专项和显式 live 分层。

## M161：Console smoke 的异步竞态和页面生命周期需要单独处理

### 现象

M161 的浏览器验收中发现四类容易把前端真实问题与 smoke 自身问题混淆的边界：动作目录异步加载完成前用户已经发起请求；降级对比数据中 `y=null` 的行仍应保留详情入口；lineage 页面历史列表包含 Action 项，不能把它们当作普通运行项；CDP smoke 的定时器没有及时清理时，脚本通过后仍会延迟退出，或在页面导航时出现 `Inspected target navigated or closed`。

### 根因

这些问题分别属于前端异步资源加载、降级数据的展示语义、历史记录类型混合和浏览器测试进程生命周期。它们不应通过扩大后端结果分支或让 smoke 忽略错误来处理；否则会掩盖结构化结果与实际 UI 状态的不一致。

### 处理与预防

动作目录请求在竞态期间自动重新加载；对比表即使没有可绘制的 `y` 值也保留详情导航；lineage smoke 只筛选普通运行历史项并保留 Action 专用入口；CDP smoke 的等待定时器在响应或异常后清理，并在页面导航/关闭时把环境边界报告为可重试错误。以后新增异步前端证据时，必须同时覆盖加载竞态、空值降级、混合历史类型、页面导航和脚本退出，不得只增加静态 DOM 断言。

## M162：Linux 容器不能直接执行宿主 PowerShell production profile

### 现象

将 `scripts/test_profile.py --profile docker` 直接放进 Linux Docker 容器执行时，profile 试图启动 `powershell.exe`，返回 `FileNotFoundError`。容器本身健康、HTTP API 和 GIS 依赖均正常。

### 根因

Docker profile 的职责是由宿主编排器调用已经运行的容器 HTTP 入口；它不是容器内部的 Python 单元测试。把宿主 PowerShell 命令当作 Linux 容器内子进程会混淆测试层次，也会让真实部署 acceptance 被错误归类为业务失败。

### 处理与预防

Python 专项、profile、compileall 和 GIS 回归使用 `docker exec ai-agent-spatial-agent-1 python ...`；production acceptance 使用宿主侧 `scripts/production_acceptance.ps1 -BaseUrl http://127.0.0.1:8088`，目标仍是当前重建 Docker 服务。测试策略文档明确区分两者，默认矩阵保持精简；以后增加跨平台 profile 时，必须声明执行面（容器内部或宿主编排）并分别提供可执行入口。

## M163：Text Domain 工厂丢弃 decision store 会让异步确认变成执行失败

### 现象

M163 新增异步“执行前确认”回归时，Text Domain 请求的 workflow selection 已经成功选择 `text_summary`，但异步运行最终为 `FAILED`，错误分类为 `tool_gate`，错误为 decision store 不可用；同步默认 Runtime 的确认测试仍然通过。

### 根因

`ServiceState` 会把公共 `decision_store` 注入自定义 runtime factory，但 `domains/text/runtime.py` 的工厂虽然接受 `**kwargs`，却没有显式接收并转交该依赖。异步 worker 因此构造出没有 DecisionStore 的 Text Runtime。

### 处理与预防

Text runtime factory 现在显式接收 `decision_store` 并传给公共 `build_runtime`；确认边界仍由 Runtime/DecisionStore 负责，Domain 不复制生命周期逻辑。以后新增 Domain runtime factory 必须验证 ServiceState 注入的 state store、conversation store、observability 和 decision store 均能到达 Runtime，并补一个异步确认专项，不要只验证同步路径。

## M163：SQLite artifact-only 恢复找到决策但无法执行 CAS

### 现象

异步确认运行的 artifact 已保存 `decision_record` 和 workflow selection，但关闭原服务、使用新的 SQLite 数据库读取 artifact 后，批准请求返回 `decision_not_found`；内存 artifact-only 恢复可以成功。

### 根因

`AgentService._decision_record()` 能从 artifact 找到记录，但 `SQLiteDecisionStore` 没有实现 `restore()`，所以记录没有重新写入新的 SQLite 决策表，后续 `resolve()` 的 CAS 查询自然找不到它。

### 处理与预防

SQLiteDecisionStore 增加受校验的恢复入口：同一 Domain 下只插入不存在的记录，不覆盖已有记录；同一 decision ID 属于其他 Domain 时拒绝恢复；插入后仍复用原有 `get/resolve/consume` 和版本 CAS。以后涉及 artifact-only 用户决策时，必须同时验证内存、全新 SQLite、跨 Domain 和过期边界，并比较恢复前后的 workflow selection、plan fingerprint 和 lifecycle evidence。

## M164：Selection interaction 专项中的错误自引用断言造成假失败

### 现象

M164 相关代码和 Console smoke 已经正确接入，但 Docker 专项出现 1 个失败：测试要求 `scripts/console_selection_interaction_smoke.js` 的文件内容包含字符串 `console_selection_interaction_smoke.js`。该失败看起来像前端入口缺失，实际与业务行为无关。

### 根因

测试把“文件路径存在”误写成“文件内容包含自身文件名”，没有断言真实的 smoke 入口。脚本本身已经正确 `require("../web/console_selection_interaction.js")`，所以这是测试断言设计错误，不是 Console 或 Runtime 回归。

### 处理与预防

断言改为检查 smoke 文件存在，并检查其真实 `require` 入口；随后 Docker 专项 16 项中 15 项通过、1 项因容器没有 Node 跳过，宿主 Node smoke 通过。以后静态前端契约应分别验证文件存在、入口引用和可执行 smoke，不应要求文件内容包含自身路径。

## M164：HTTP 交互验收必须使用匹配的 Domain 请求

### 现象

使用 HTTP 默认 GIS Domain 提交“概括一段文本”并要求确认时，返回 `facts_required`，而不是 `confirmation_required`；直接 Text Domain 单测对同类请求则进入确认态。

### 根因

HTTP 生产服务默认绑定 GIS Domain。该请求没有空间事实，GIS Domain 按能力发现契约返回结构化缺失事实；Text 单测使用显式 Text runtime factory，两条路径的 Domain 不同。`require_confirmation` 本身已在 HTTP `run_kwargs` 中正确透传，并未丢失。

### 处理与预防

改用 HTTP 默认 GIS Domain 支持的“查询DEM栅格元数据”请求验证真实确认 → `POST /runs/{id}/interaction` `confirm` → `COMPLETED`，同时验证非法 action 返回 400、interaction GET 不泄露原始请求/工具参数。以后 HTTP/Console 验收必须显式记录 Domain、planner、backend 和 workflow；跨 Domain 对比应通过 Domain Pack seam，不要用不匹配的请求推断生命周期实现错误。

## M165：生产 HTTP 未提供 Console 外部 JS 资源导致动态交互空白

### 现象

M165 的真实 Chrome smoke 中，HTTP 运行已经返回 `WAITING_FOR_DECISION`，完整 run 的 `result.selection_interaction.state` 也是 `confirmation_required`，但页面没有交互卡片，`window.ConsoleSelectionInteraction` 未加载。

### 根因

生产 FastAPI 和开发 HTTP 只提供 `/`、`/index.html`、API 与 artifact 路由，没有为 `index.html` 中的相对路径 `console_nested_schema.js`、`console_decision_evidence.js` 和 `console_selection_interaction.js` 提供静态资源路由。浏览器拿到 404 后，页面 fallback 为空态；容器文件存在不能证明 HTTP 资源可达。

### 处理与预防

开发与生产入口新增同形的受限 Console JS allowlist，只允许三个已知文件并返回 `application/javascript`，不接受任意路径或目录遍历。新增 `scripts/console_selection_interaction_browser_smoke.js`，先检查真实资源 HTTP 200，再通过 CDP 断言 `confirmation_required` 卡片和 confirm/reject/cancel。以后新增外部前端模块必须同时验证：仓库文件、容器文件、HTTP 资源状态、浏览器加载状态和实际 DOM 行为；静态 Node smoke 不能替代资源路由验收。

## M166：跨入口 request identity 因语义上下文未持久化而漂移

### 现象

新增 `request_identity` 后，Docker production acceptance 在 `async/artifact` Contract Harness 处发现同一异步请求的 `request_identity.fingerprint` 不一致。同步结果、async polling 和 artifact 都能单独完成，但跨入口比较失败。

### 根因

request identity 需要包含 `spatial_context`，因为它属于请求语义；同步 Service 在构建 result envelope 时拥有该上下文，而 `AgentRunResult` 的 SQLite 快照原先没有保存它。async polling 从快照重建契约时只能看到请求文本和 runtime context，artifact-only recovery 也无法重新得到完整语义上下文，于是同一请求被哈希成不同身份。另一个兼容性问题是 replay fixture 使用短的 `sha256:plan-a` 形式，若只接受完整 64 位摘要会把合法的脱敏回放误判为 unavailable。

### 处理与预防

新增版本化 `spatial-agent.request-identity.v1`，只哈希 request、resolved_request、workflow 和 spatial_context，排除 session、Planner、backend、状态、时间和密钥；result、async、artifact、recovery 和 Contract Harness 共用该身份。`AgentRunResult`、SQLite 反序列化和 ArtifactStore 持久化现在保留 normalized spatial context；async 重建优先使用持久化快照，并以提交 job payload 作为兼容回退。生产生成的 plan identity 仍使用完整 SHA-256，同时允许有界、无敏感内容的短 replay 标识。以后新增影响请求语义的字段，必须同时检查模型快照、artifact、async 重建和 Contract Harness，不能只给同步 result 加字段。

## M166：显式 workflow 选择被自然语言路由覆盖会产生错误结果契约

### 现象

用户在交互界面明确选择 `spatial_analysis` 后，HTTP 运行仍可能生成 `admin_raster_composite` 的两步计划，最终返回 `result type is not allowed by template: zonal_raster_statistics_result`。同一个 `spatial_analysis` 模板直接编译时，模板自身的结果类型和 DAG 均正确。

### 根因

GIS Rule Planner 原先只把显式 workflow 的约束追加到请求提示文本，随后再次执行自然语言能力路由。短请求“进行空间分析”没有足够任务词时会被重新匹配为栅格统计能力，导致 Planner 输出与用户已选择的 workflow 不一致；Runtime 的严格校验只是正确地拦截了这个漂移。

### 处理与预防

GIS Domain 新增 `RuleBasedPlanComposer.compose_workflow()`，显式 workflow 直接通过现有模板编译器生成约束、证据、DAG 和 output type；Runtime、ToolRegistry 和最终 workflow 校验保持不变。新增 M166 回归覆盖显式选择 `spatial_analysis` 的计划类型和 9 个工具步骤，并用 Docker 复现原始失败后验证修复。以后显式选择必须优先于自然语言自动路由，不能把结构化用户决策降级为提示词；新增 workflow selection 时必须同时测试短请求、完整请求和结果契约一致性。

## M166：上下文裁剪后旧版能力证据别名缺失

### 现象

复杂空间请求执行成功，新的 `workflow_selection` 结构化证据也存在，但历史 M77 客户端读取 `plan_evidence.selected_capability_id` 时出现 `KeyError`。原因是 compact context 裁剪后，旧版顶层能力字段没有生成。

### 根因

能力发现和 workflow selection 已经迁移为领域无关的嵌套契约，但旧版顶层字段只在未被裁剪的 verbose `capability_discovery` section 存在。上下文预算控制改变了展示 section 的可用性，却不应改变已选能力的公共结果语义。

### 处理与预防

Runtime 在缺少 verbose discovery section 时，从同一 `workflow_selection` projection 生成有界的兼容别名；没有新增第二套选择逻辑，也没有引入 GIS 字段。M166 相邻 Docker 回归 57 项中 56 项通过、1 项因容器未安装 Node 跳过。以后压缩或迁移 evidence 时，必须区分 canonical nested contract 与兼容投影，并在 context budget 裁剪场景下验证两者仍表达同一选择结果。

## M166：交互续接重复消费 pending request 导致身份漂移

### 现象

空间请求首次进入 `facts_required` 后，通过 `POST /runs/{run_id}/interaction` 提交事实或选择 workflow，运行可以继续执行，但 `resolved_request` 变成了“分析空间数据 分析空间数据”。因此 request fingerprint、plan fingerprint 和跨入口 Contract Harness 可能与同一 workflow 的直接运行不一致。

### 根因

澄清失败时，ConversationStore 会保存当前的 `resolved_request` 作为 pending request。交互动作本质上是对已有 run 的继续处理，不是新的用户轮次；但 `AgentService.apply_run_interaction()` 原先使用原始 `request` 重新调用 `Service.run/preview`，而 Runtime 的 `_resolve_request()` 又把 pending request 拼接一次，形成重复语义。

### 处理与预防

selection/facts/preview 动作现在先通过所选 Runtime 消费当前 session 的 pending clarification，再使用当前 run 持久化的 `resolved_request` 继续进入 Runtime；确认、拒绝、重试、恢复和取消仍沿用各自生命周期。新增 M166 回归覆盖 `provide_facts`、`select_workflow`、同步直接运行与 SQLite 临时状态隔离，并用 Contract Harness 验证两条路径差异为空；真实 Chrome smoke 同时验证确认→完成、补事实→完成和恢复→完成。以后新增交互动作必须明确区分“新对话轮次”和“已有 run 续接”，并比较 request identity、plan identity、trace、artifact 和 evidence，不能只断言最终 status。

多轮场景还必须保留两个字段的职责：`request` 是当前用户轮次，`resolved_request` 是已合并的会话语义。交互续接通过 Runtime 的内部 resolved-request override 传递后者，不得把后者覆盖到前者；HTTP 公共 payload 不开放该内部参数。

## M166：候选能力记录存在但未形成真实选择生命周期

### 现象

Domain discovery 可以返回多个 `candidate_ids`，但如果同时保留第一项 `selected_capability_id`，Runtime 会继续规划和执行，前端只能展示候选列表，无法证明用户真正选择过能力。

### 根因

候选发现是描述性证据，是否能够安全自动选择属于 Domain 策略；公共 Runtime 原先没有消费 Domain 声明的歧义状态，也没有在 Planner 前建立统一的候选选择门控。

### 处理与预防

允许 Domain 在 `select_workflow` 投影中声明 `state=ambiguous`。Runtime 只负责把它转换为 `NEEDS_CLARIFICATION` 和 `candidate_selection` 交互，不解释能力 ID，也不执行工具；显式 workflow 和 `select_capability` 选择仍经过同一 Runtime/Planner/ToolRegistry 路径。以后新增候选路由必须分别测试自动选定、歧义澄清、用户选择后的续接以及跨入口 selection evidence，不能只断言候选数组存在。

## M166：公共 Service workflow 边界泄漏 GIS 模板

### 现象

非 GIS Domain 通过交互提交自己的 workflow 时，Service 的公共 normalizer 直接调用 GIS 模板目录，未知 Text workflow 被报为 `unknown workflow template`；Runtime 计划校验也直接使用 GIS 模板规则。

### 根因

workflow 规范化和执行前校验被放在 Service/Runtime 公共入口，早期 GIS 模板实现成为隐式默认策略，导致 Domain Pack 虽然存在，跨 Domain 的选择和恢复仍无法真正替换。

### 处理与预防

新增 Domain-owned `normalize_workflow`、`validate_workflow_plan` 和 `resolve_capability_selection` seam。GIS Domain 在 seam 内调用原有模板目录，Text Domain 只实现自己的通用形状校验和能力映射；公共 Service 仅转发选中的 Domain，旧自定义 Domain 保留有界兼容回退。以后新增 workflow、能力选择或结果类型，必须确认 HTTP、async、interaction、recovery 和 Runtime 校验均通过 Domain seam，公共层不得导入 GIS 模板或能力名称。

## M167：Runtime 上下文代码缩进错误会让 Docker 容器反复 unhealthy

### 现象

M167 在 `agent/runtime.py` 的上下文构建函数中加入候选详情参数后，镜像可以成功构建，但容器启动失败，健康检查持续返回 `unhealthy`，生产 HTTP 和所有容器测试都不可用。

### 根因

补丁将 `workflow_selection` 调用块多缩进了一层，Python 在导入 `agent.runtime` 时抛出 `IndentationError`。Docker build 只复制文件并不等于应用可以导入；Uvicorn 子进程不断重启，健康检查看到的只是连接拒绝。

### 处理与预防

修正缩进后重新执行当前工作树的 Docker build/recreate，确认容器 `healthy`，再运行 Docker `compileall`、专项测试和 production acceptance。以后修改 Runtime 这类高扇出模块时，提交前至少按顺序执行：容器内 compileall → 容器内最小专项 → 健康检查 → HTTP acceptance；不能只依据镜像构建成功判断服务可用。若容器 unhealthy，先读 `docker logs` 和 `.State.Health`，区分导入错误、健康检查连接错误和业务测试失败。

## M167：候选 ID 直接展示无法形成通用能力选择

### 现象

workflow selection 虽然返回了 `candidate_ids`，但 Console 只能显示代码字符串；选择动作会统一打开 GIS workflow editor，无法让用户理解候选能力，也无法证明实际提交了哪个 capability。

### 根因

selection evidence 只有选择结果，没有对候选能力的有界名称、描述、输入事实、结果类型、可执行 workflow 和动作信息；前端因此不得不依赖旧的 GIS 编辑器流程，违背了 Domain-neutral renderer 要求。

### 处理与预防

在 `spatial-agent.workflow-selection.v1` 中增加有界 `candidate_details`，由 Domain capability catalog 提供候选元数据，公共投影只负责安全裁剪和版本化规范化。Console 根据详情渲染候选卡片，选择卡片直接提交 `capability_id`，仍保留没有详情时的旧兼容路径。以后新增候选能力必须同时检查 catalog、selection evidence、interaction、HTTP/async/artifact 恢复和浏览器实际动作，不能只增加候选 ID 或前端专用分支。

## M169：交互续接没有 CAS 会重复创建子运行

### 现象

候选能力卡片、补充事实或预览动作在网络重试、浏览器双击或多 worker 并发时，会对同一个 `NEEDS_CLARIFICATION` run 再次调用 `AgentService.run/preview`，产生多个语义相同的续接运行；普通 async 的 `idempotency_key` 不能覆盖这种同步交互路径。

### 根因

交互动作原先只有 allowlist 和 Domain workflow resolver，没有持久化“源 run 已消费哪个 action、输入是什么、结果是哪一个子 run”的原子记录。源 run 本身仍保持澄清状态，因而单独检查状态无法实现 compare-and-swap。

### 处理与预防

新增 `interaction_receipts` SQLite 表和 memory fallback，以 `domain_id + source run_id + action` 为 CAS 主键、以幂等键为重放边界。`select_capability`、`select_workflow`、`provide_facts`、`preview` 在进入 continuation Runtime 前先 reserve，成功后记录子 run 或预览响应；重复输入重放，冲突输入拒绝，服务重启从 receipt 和 run snapshot/artifact 恢复。以后新增交互动作必须先定义 source subject、输入 fingerprint、CAS 主键、IN_PROGRESS 崩溃语义和恢复证据，不能只复用普通 run 的幂等逻辑。

## M169：服务关闭没有释放 Observability 文件句柄

### 现象

Docker 专项业务断言均通过，但测试输出持续出现 `ResourceWarning: unclosed file ... observability.log`，尤其在异步、多轮交互和 SQLite 恢复场景中反复出现。

### 根因

`ObservabilityEmitter` 已经提供 `close()`，但 `AgentService.close()` 只停止 reaper 和线程池，没有转发关闭调用；每个 Service 实例打开的日志流直到解释器回收才释放。

### 处理与预防

Service 关闭流程现在显式调用 `self._state.observability.close()`，保证测试和进程重启释放句柄。以后新增可持有文件、网络或线程资源的 Runtime 依赖，必须由 Service 生命周期统一关闭，并在 Docker 测试中检查无新增 `ResourceWarning`。

## M169：生产入口全局 Service 未接入关闭生命周期

### 现象

生产 API 在模块导入时创建全局 `AgentService` 并启动 reaper。直接导入生产模块的契约测试不会触发 ASGI 生命周期，进程结束时可能出现 observability 文件句柄未关闭的 `ResourceWarning`。

### 根因

服务已经具备显式 `close()`，但生产入口没有注册 shutdown 处理；测试中替换临时 Service 也不能替代模块级 Service 的所有权释放。

### 处理与预防

生产入口现在使用 FastAPI `lifespan` 管理应用生命周期，并保留 `atexit` 兜底；开发 HTTP 入口也为 `AgentApiHandler` 的默认 Service 注册退出释放，确保 ASGI、标准库 HTTP 和直接模块导入三条路径都释放 Service 资源。接入 FastAPI 生命周期时应先检查 pinned 版本是否支持 `lifespan`；不能假设 `add_event_handler()` 存在，也不应继续使用已弃用的 `on_event()`。以后新增全局 Service、线程池、文件或数据库句柄时，必须同时覆盖应用 shutdown、直接导入测试和重复 close 场景。

## M169：开发门禁测试未关闭临时 Service

### 现象

Docker quick 的业务断言全部通过，但测试结束时仍出现 `observability.log` 文件句柄未关闭的 `ResourceWarning`。该问题只在开发门禁的临时 Service 生命周期中出现，容易被误判为 Runtime 或 Docker 业务失败。

### 根因

`tests/test_dev_gate.py` 创建了多个 `AgentService`，HTTP server 关闭时只停止线程池，没有把 Service 作为测试资源注册清理；M169 虽然已补齐 `AgentService.close()`，但测试没有调用它。

### 处理与预防

开发门禁现在使用 `self.addCleanup(service.close)`，并移除重复的内部线程池关闭调用。以后测试中创建 Service、SQLite store、HTTP server 或 observability emitter 时，必须通过 `addCleanup`/`finally` 明确释放所有权；阶段 quick 应在 Docker 内检查 stderr，不应只看 unittest 的返回码。

## M169：浏览器 smoke 的 Node 模块入口依赖隐式推断

### 现象

更新真实 Chrome CDP smoke 后，直接执行 `node scripts/console_selection_interaction_browser_smoke.js` 在当前仓库失败，错误为 `SyntaxError`；浏览器和 HTTP 服务本身均正常。

### 根因

仓库没有 `package.json` 声明模块类型，Node 按 CommonJS 解析 `.js` 文件。脚本使用顶层 `await`，不能依赖 Node 根据语法或未来环境配置自动推断为 ES module。

### 处理与预防

浏览器 smoke 现在使用显式异步 IIFE，并在入口统一捕获异常、设置退出码；宿主 Node `--check`、真实 Chrome CDP 和 Docker HTTP 均通过。以后新增 Node smoke 必须明确模块入口（CommonJS 异步 IIFE 或仓库显式 ESM 配置），并在没有 `package.json` 的干净环境中直接执行一次 `node script.js`，不能只在开发机的隐式模块环境中验证。

## M170：生命周期专项误依赖未安装的 TestClient

### 现象

M170 生命周期专项第一次执行时，业务代码已经可以导入，但测试在导入 `fastapi.testclient.TestClient` 时失败，提示需要安装 `httpx2`。当前生产镜像没有该额外依赖，失败与 Agent Runtime 或 FastAPI lifespan 行为无关。

### 根因

为了测试 ASGI shutdown，测试直接引入了 Starlette TestClient；而项目的生产 requirements 有意保持精简，未安装 TestClient 所需的 `httpx2`。这会把测试工具依赖误当成产品运行时依赖。

### 处理与预防

测试改为使用 FastAPI 原生 `app.router.lifespan_context(app)`，在异步上下文中验证 Service close，不新增生产依赖；M170 专项和 production acceptance 均通过。以后生命周期测试应优先调用框架公开的 lifespan seam；只有明确加入独立测试依赖并记录到测试 profile 时，才使用 TestClient，不得为了单个专项修改生产镜像依赖。

## M171：旧持久化记录缺少 Domain 时被误归为 GIS

### 现象

Text 或未来 Domain 使用共享 SQLite/artifact 存储时，旧 snapshot、旧 async job 或旧 artifact 没有 `domain_id`，恢复和列表过滤会把它们默认为 GIS，造成跨 Domain 数据不可见、run identity 归属错误或错误的“属于其他 Domain”拒绝。

### 根因

早期兼容代码在 `ArtifactStore`、`SQLiteStateStore`、结果反序列化和 Service recovery 中散落使用字面量 `"gis"`。公共持久化 adapter 不知道当前 Domain，却替 Domain 做了业务归属决策。

### 处理与预防

为 `ArtifactStore`、`SQLiteStateStore` 增加有界 `legacy_domain_id`，由 `AgentService` 将选定 Domain 传入隐式 adapter；显式传入的共享 store 保留自身兼容配置。所有 snapshot、async、artifact、decision 和 recovery 读取使用同一归属，并将 SQL fallback 改为参数化值。以后新增持久化字段时，必须同时验证旧数据读取、Domain 过滤、异步接管、artifact-only recovery 和跨入口 fingerprint，公共层不得凭 GIS 字段推断业务领域。

## M171：前端 bootstrap readiness 等待历史大结果渲染导致 smoke 偶发超时

### 现象

Console 页面 HTTP、外部 JS 和所有初始化接口均返回成功，但浏览器 smoke 在 20 秒窗口内持续看到 `__consoleBootstrapReady === false`，报“Console 页面脚本未就绪”；再次运行或手动等待后可能通过。

### 根因

页面把 bootstrap 标记放在 `Promise.all(...).then(()=>restoreSession()).finally(...)` 的末端。`restoreSession()` 会加载历史、完整运行结果、GeoJSON 和 runtime evidence，并进行大量同步 DOM/地图渲染；它是可延迟的用户体验工作，却被错误当成基础控件就绪条件。

### 处理与预防

基础目录 Promise 完成后立即设置 readiness，随后后台执行 `restoreSession()`；失败时也把页面置为可交互并由各自空态展示降级。浏览器 smoke 同时检查版本标记、真实函数入口和 DOM 控件，不依赖 lexical 全局变量 `$`。以后新增启动任务必须区分“能否接收用户动作”和“历史/证据是否完全恢复”，并用真实 Chrome 在冷启动和已有历史两种状态验证。

## M171：相邻测试通过但未关闭 Observability 句柄

### 现象

M60/M61/M67 的业务断言全部通过，但 Docker stderr 出现 `ResourceWarning: unclosed file ... observability.log`；只看 unittest 返回码会把资源泄漏误认为阶段通过。

### 根因

部分旧回归直接创建 `AgentService`，或只调用内部 `_async_executor.shutdown()`，没有调用公开的 `AgentService.close()`；因此线程停止了，但 `ObservabilityEmitter` 文件句柄仍由解释器回收。

### 处理与预防

为临时 Service 注册 `self.addCleanup(service.close)`，并将手动 executor shutdown 改为公开 close；阶段回归增加 `python -W error::ResourceWarning` 的 Docker 运行，确保生命周期错误直接失败。以后测试中的 Service、HTTP server、SQLite store 和 emitter 必须明确所有权和 finally/cleanup 路径，不能只验证业务状态。

## M172：catalog matcher 接入后复杂 context 裁剪掉关键能力证据

### 现象

能力目录增加请求提示和候选详情后，复杂空间请求的业务计划仍能执行，但 `context_evidence` 将 `capability_discovery`、`capability_catalog` 或 workflow template 标记为 omitted；HTTP/artifact 契约因此缺少能力目录或精确模板证据。

### 根因

`ContextBuilder` 只按整体字符数淘汰 section。workflow templates、selection candidate details、工具 schema、memory 同时存在时，旧的淘汰顺序会先丢掉能力发现/目录，且没有区分“规划时的 compact context”和“结果中需要保留的结构化证据”。

### 处理与预防

Runtime 增加领域无关的 selected selection/template compact projection：保留完整 candidate IDs/count，只保留选中详情和选中模板；context budget 在不足时优先淘汰可选 memory、workflow 模板冗余和低优先级工具信息，保留 discovery/catalog/selection 证据。新增 M172 HTTP/artifact 回归验证动态 catalog fallback 的 `raster_metadata_result`、plan identity 和 artifact contract 一致。以后新增 evidence 字段时，必须同时验证 context budget 充分、planner 可见字段和持久化结果字段，不能只在未超预算的短请求上断言。

## M172：HTTP 契约测试直接发送中文字符串导致伪装成服务失败

### 现象

新增动态发现 HTTP 测试第一次执行时，服务尚未收到请求，`http.client` 在发送包含中文的 JSON 字符串时抛出 `UnicodeEncodeError`；容易误判为 HTTP 入口或 Agent Runtime 失败。

### 根因

`HTTPConnection.request()` 对字符串 body 默认按 Latin-1 编码。测试请求声明了 JSON content type，但没有先将 `ensure_ascii=False` 的 JSON 文本编码为 UTF-8 bytes。

### 处理与预防

测试改为显式 `json.dumps(..., ensure_ascii=False).encode("utf-8")`，并继续通过服务真实 HTTP 入口验证响应。以后 HTTP/PowerShell/浏览器验收遇到中文请求失败时，先区分请求体编码、网络传输和服务业务错误；契约测试必须显式指定 UTF-8 bytes，不能依赖客户端默认编码。

## M173：compact context 丢失已知能力绑定导致模型错配被误报为 unresolved

### 现象

模型针对“查询 DEM 栅格元数据”返回了行政区边界计划。此前 Planner selection evidence 返回 `unresolved`，而不是应有的 `mismatch`。这会让面试演示和 live/replay 评测无法区分“模型选择了一个已知但不符合当前请求的能力”和“模型输出了 Domain 完全不知道的结果类型”。

### 根因

M172 为控制 Planner 上下文大小，只保留选中能力的完整候选卡片和选中 workflow 模板。`planner_selection` 原本只从这些详细卡片读取 result type；因此已知的其他能力虽然存在于 Domain catalog，却不在 alignment 输入中。第一次补丁仅从现有候选详情生成摘要，仍然无法覆盖被 compact projection 隐藏的其他 catalog 能力。

### 处理与预防

现在由 Domain catalog 生成有界 `known_capability_result_types`，只包含能力 ID 与结果类型，不参与能力选择，也不展开工具或数据细节；`planner_selection` 使用它补充已知结果类型绑定。已知能力错配稳定返回 `mismatch`，未知结果类型仍返回 `unresolved`，多候选仍由 workflow selection 在 Planner 前返回 `ambiguous`。Contract Harness 新增稳定的 `planner_selection` 和脱敏 `repair_lineage` 投影，排除 latency/occurred_at 等易变字段但保留修复语义。以后做 context 压缩时，必须分别验证模型输入预算、候选选择证据和 Planner alignment 证据，不能用“候选详情存在”替代“已知能力索引完整”。

## M175：扩展 Evidence Registry required entries 必须升级完整性版本

### 现象

selection evidence 已经存在于 `result.planning`，但旧的 Evidence Registry completeness 只要求五个核心 entry。若直接增加 Registry entry 却继续返回 `spatial-agent.evidence-completeness.v1`，下游无法判断 v1 是旧契约还是已经包含 selection 的新语义，旧 artifact 与当前严格验收也会产生不透明差异。

### 根因

Registry 的 schema（可兼容读取的索引）与 completeness contract（当前版本必须具备哪些 entry）职责不同；早期实现只考虑新增可选 Domain evidence，没有把 required entry 集变化视为公共契约迁移。

### 处理与预防

M175 保持 `spatial-agent.evidence-registry.v1` 的安全 normalize 兼容，新增 workflow/planner selection entry，并将严格完整性投影升级为 `spatial-agent.evidence-completeness.v2`。旧 Registry 可以读取，但缺少当前 selection entry 时只允许兼容展示，不能通过当前 replay/live/Contract Harness 完整性门禁。以后改变 required entry、引用规则或完整性判定时，必须升级 completeness 版本，并同时覆盖旧 artifact、未知版本、同步、异步、artifact-only recovery、Text/GIS 和前端证据状态。

## M177：跨入口 Evidence Projection 不应携带 transport source

### 现象

开发 HTTP 的 `/runs/{id}/evidence` 与 `/artifacts/runs/{name}/evidence` 返回的 Registry、selection 和完整性内容相同，但整体 projection equality 断言失败；唯一差异是 projection 中的 `source` 分别为 `run_evidence` 和 `artifact_http`。

### 根因

transport 来源是观测上下文，不是请求的核心证据语义。将它放进共享 projection 会让同步、异步、Artifact 和不同 HTTP 路径在没有业务差异时产生结构化漂移，违背跨入口一致性契约。

### 处理与预防

新增 `spatial-agent.evidence-projection.v1` 后，移除 transport-specific `source` 字段；共享 projection 只保留 Registry、completeness、selection 和 migration 状态。入口日志仍可在外层记录来源，不能把传输元数据混入需要 equality 比较的公共证据。以后新增公共 evidence 字段时，先判断它是核心语义、Domain 证据还是 transport 观测；只有前两者进入跨入口 projection。

## M176：浏览器 smoke 继承表单状态导致空间总览被错误路由

### 现象

在 Docker 生产服务和前端模块均正常时，`console_overview_smoke.js` 发送“分析洪山区空间概况”却得到已完成的单工具 `dem` 结果，空间总览面板没有显示。相邻的候选选择浏览器 smoke 可以正常通过。

### 根因

浏览器 smoke 复用了 CDP 页面，页面导航不会保证浏览器表单控件恢复到默认值。空间总览脚本只固定了 backend，没有固定 planner；前一个 smoke 或浏览器自身的表单恢复可能把 planner 留在其他值，导致测试请求与预期的确定性 Rule Planner 路径不一致。这个失败不是 Evidence Registry renderer 或 GIS 几何执行失败。

### 诊断

先查看 smoke 返回的 `decision`、步骤数和 `result_type`。如果状态为已完成但步骤数为 1、结果不是 `spatial_overview_result`，再在 CDP 中检查 `$('planner').value` 与 `$('backend').value`，区分页面状态继承和服务业务错误。

### 修复

`console_overview_smoke.js` 增加 `CONSOLE_PLANNER` 参数，默认显式设置为 `rule`，与已有 backend 一样在发送请求前固定测试输入。生产接口和运行时逻辑无需修改。

### 预防

浏览器 smoke 必须显式设置所有影响路由的 planner、backend、workflow、确认开关和会话，并使用独立会话；不能假设 Page.navigate 会清除表单状态。结果断言同时检查状态、result type、工具步骤和目标面板，避免把“任意成功结果”当作场景验收通过。

## M179：多轮评测 summary 不能与单条 Evidence Projection 同名

### 现象

M179 将统一 `evidence_projection` 接入 replay/live 评测后，离线 replay 的单条结果均为当前 Registry 且完整性通过，但顶层 projection summary 错误显示 `unavailable`，阶段断言失败。

### 根因

多轮 `repair_evidence` 同时包含“每一轮的单条 projection”和“整个 replay 的聚合 summary”。两者都使用 `evidence_projection` 字段名，收集器把缺少 `migration`、`evidence_registry_completeness` 的 summary 当作单条 projection，产生伪造的 unavailable/failed 计数。

### 处理与预防

M179 将多轮聚合字段命名为 `evidence_projection_summary`，单条证据仍使用 `evidence_projection`；收集器只有在对象同时包含 `migration` 和 `evidence_registry_completeness` 时才接受为单条 projection。以后新增聚合 evidence 时，必须区分“单条版本化证据”和“跨条目统计摘要”，不能只依赖字段名称；测试应同时覆盖真实当前状态、`unavailable` 状态和旧/未知 schema。

### 补充：过滤集合修改必须同时检查推导源和消费集合

在修复 `unavailable` 不应阻断当前结果时，第一次只替换了列表推导的消费集合，误把推导源也改成尚未定义的 `evaluated`，造成 replay 汇总 `UnboundLocalError`。处理方式是先从完整 `projections` 建立 `evaluated`，再让最终通过判断只消费 `evaluated`；以后修改两阶段过滤逻辑必须同时覆盖变量定义顺序和空集合测试，不能只看最终布尔表达式。

## M180：并行浏览器 smoke 竞争共享 CDP 页面

### 现象

同时启动空间总览 smoke 和候选交互 smoke 时，两个脚本会连接同一个 Chrome CDP 页面并互相导航、修改表单或关闭连接，偶发出现 `UnknownProcessId`、页面状态错乱或结果断言不稳定。单独串行执行时业务和页面均正常。

### 根因

两个 smoke 都默认使用 `127.0.0.1:9222` 的第一个 page。CDP 页面不是并发安全的测试 fixture，脚本之间没有独立 tab、锁或会话隔离；这属于验收编排竞争，不是 Agent Runtime 或前端 recovery 逻辑错误。

### 处理与预防

阶段验收改为串行执行共享 CDP 的浏览器 smoke，并在每个脚本中显式设置 planner、backend、workflow、会话和关键表单状态。以后若要并行浏览器验收，必须先为每个脚本启动独立 CDP 端口和独立 Chrome profile，不能仅依赖不同 Node 进程连接同一 page；看到 `UnknownProcessId` 时先检查 CDP 竞争，再判断业务失败。

## M181：Docker 未重建导致测试代码与工作树不一致

### 现象

为 M151 测试补充 `AgentService.close()` 清理后，宿主工作树已经有 `addCleanup`，但 Docker 中运行的 `-W error::ResourceWarning` 仍报告多个 `observability.log` 未关闭；对象级探针显示容器仍运行旧测试代码。

### 根因

Docker 镜像在本地测试补丁之前已经构建完成，`COPY . /app` 使用了旧层。只看宿主 diff 或直接复用旧容器，会把旧实现的警告误判为当前补丁无效。

### 处理与预防

按项目约定使用 `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --force-recreate` 重建，并确认容器为 healthy 后再测试。阶段验收记录必须标明镜像是否按当前工作树重建；修改代码后不能把旧容器结果当作新代码证据。

## M181：Action Receipt 只在响应和 Artifact 时无法证明 SQLite history 一致

### 现象

M181 初版已经在 Service response 和 Artifact 输出 `action_receipt`，但 `AgentRunResult` 没有保存该字段，SQLite history 也没有展示动作回执；重启后业务结果可恢复，却无法证明历史入口保留同一动作证据。

### 根因

交互 receipt 的完成发生在 `run()` 持久化结果之后，公共结果模型没有动作回执字段；SQLite history 只投影运行快照，没有从 `interaction_receipts.result_run_id` 关联已完成动作。

### 处理与预防

将 bounded `action_receipt` 纳入 `AgentRunResult` 和 SQLite 反序列化；history 优先读取快照字段，旧快照缺失时按 `result_run_id` 参数化查询 interaction receipt 并使用公共 normalize 投影。以后新增跨入口证据字段，必须同时验证 Service、Artifact、history、HTTP、重启恢复和旧数据兼容，不能只测试即时响应。

## M182：Service 生命周期入口没有复用统一 Action Receipt

### 现象

取消、重试和决策确认虽然已有公共动作描述，但 Service 入口仍各自直接调用 Runtime 或 DecisionStore，导致这些动作没有统一的幂等键、失败回执和跨重启 replay 证据。

### 根因

M181 先统一了动作 projection，却没有把 reserve/complete 的 CAS 调用提升为 Service 内部公共 seam；继续在每个入口复制逻辑会重新形成多个生命周期协议。

### 处理与预防

新增 `_reserve_action_receipt()` 和 `_complete_action_receipt()`，复用 `ServiceState`/SQLite 原有 `interaction_receipts` CAS 表；cancel、retry、approve/reject 均通过同一 seam 完成。以后新增生命周期入口，必须先接入 Action Receipt，再实现具体 Runtime/Domain 动作。

## M182：无幂等键的 retry 被旧失败 receipt 永久阻断

### 现象

第一次 retry 执行失败后，同一 run 的第二次 retry 即使底层故障已恢复，也会因为 `(domain_id, run_id, action)` 已有 FAILED receipt 而无法再次执行。

### 根因

原 interaction receipt 的 CAS 设计默认一个 source run/action 只有一次交互；retry 的语义却允许用户不提供显式幂等键时发起新的真实尝试。

### 处理与预防

保持同一 receipt 表和 CAS seam，仅对“未传显式幂等键且 action 为 retry”的 FAILED 记录执行受控 reopen，生成新的内部幂等键并清理旧结果引用；显式幂等键仍保持 replay/冲突语义。以后要区分“安全重放”和“用户要求的新尝试”，不能简单复用同一个 idempotency key。

## M182：动作完成后 Artifact 与 SQLite history 证据漂移

### 现象

Action Receipt 已能写入即时响应和 SQLite snapshot/history，但对已经导出的 run，取消或决策动作完成后旧 Artifact 仍缺少最新回执。

### 根因

`_persist_action_receipt()` 原来只更新 AgentRunResult 和 SQLite；ArtifactStore 没有“给已有 run artifact 附加 bounded receipt”的公共写入 seam。

### 处理与预防

新增 `ArtifactStore.attach_action_receipt()`，在已有 Artifact 存在时重写受限的 `action_receipt` projection，并增加 Artifact/history equality 测试。以后新增跨入口状态字段，必须覆盖“已有 Artifact + 动作完成后更新”的场景；Artifact 不存在时仍按可恢复降级处理，不能重新执行动作。

## M182：compact discovery 的 HTTP 测试未释放 Service 公开资源

### 现象

Docker compact discovery 的业务测试通过，但进程退出时出现 `observability.log` 未关闭的 `ResourceWarning`。

### 根因

`tests/test_http_contract.py` 直接调用私有 `_async_executor.shutdown()`，没有关闭 `AgentService` 持有的 Observability emitter；只停止线程池不能释放全部 Service 资源。

### 处理与预防

改为调用公开 `AgentService.close()`，并在 Docker 中使用 `python -W error::ResourceWarning` 和 compact discovery 验证无警告。以后测试只能通过公开 close/cleanup seam 释放 Service、SQLite、HTTP handler 和 emitter，不能只关闭内部线程池。

## M183：Action Receipt 不应无条件进入默认 Result Contract equality

### 现象

将 Action Receipt 直接加入默认 `normalize_result()` 后，已有“先提供 facts 再继续执行”和“直接执行同一工作流”的跨入口测试被判定为结果漂移；差异来自动作 ID、幂等输入和动作状态，而不是最终 Result/Evidence。

### 根因

Action Receipt 描述的是导致结果产生的生命周期动作，属于 transition evidence；Result Contract 描述的是请求理解、计划、执行和结果证据。两者虽然共享 schema 词汇，但不是同一个 equality 维度。

### 处理与预防

在同一个 `evaluation.contract_harness` 模块中增加独立的 `ActionReceiptContract`、`normalize_action_receipt_contract()` 和 `compare_action_receipts()`，只在动作入口比较动作语义；默认 Result equality 不携带 Action Receipt。以后新增跨入口证据字段时，必须先判断它属于结果语义还是触发结果的 transition，不能为了“字段都比较”把正交契约混在一起。

## M183.2：Action Receipt linkage 在导入阶段形成循环依赖

### 现象

新增 Action Receipt 与 Request/Plan/Result/Evidence 的关联投影后，Docker 生产服务启动失败，容器无法进入 `healthy`。错误链路是 `recovery_action -> action_identity -> evidence_projection -> action_lifecycle -> recovery_action`。

### 根因

`recovery_action` 是 Runtime 初始化阶段最早加载的公共模块；如果它在模块顶层导入依赖 Evidence Projection 的 linkage normalizer，Evidence Registry 又会加载 Action Lifecycle，最终在 `recovery_action` 尚未定义完 `normalize_action_ids()` 时回到该模块，触发 partially initialized module 错误。

### 处理与预防

将 linkage normalizer 改为 `project_action_receipt()` 内的惰性导入，保持启动阶段的动作 allowlist 与证据投影不互相初始化；Docker 重建后容器恢复 healthy。以后新增公共投影时，必须画出模块导入图并在生产容器启动测试中验证，不能只运行未触发完整 HTTP import 的单元测试。

## M183.2：SQLite Action Receipt replay 可能丢失 identity linkage

### 现象

取消动作首次响应、Artifact 和 SQLite history 均有 identity linkage，但服务重启后使用同一幂等键 replay 时，返回的 Action Receipt 只剩动作字段，缺少 Request/Plan/Result/Evidence linkage。

### 根因

SQLite `interaction_receipts` 的 CAS 行只保存动作幂等字段和 `result_run_id`。取消入口同时提供了一个不含新回执的最小 `response_payload`，replay 优先读取该 payload，因此不会继续读取已持久化的 result snapshot；随后从 CAS 行重新投影时自然没有 linkage。

### 处理与预防

完成动作时，将 bounded identity linkage 同步写入带有最小响应的 `response_payload`；有 result reference 的动作仍同步写入 AgentRunResult/Artifact。replay 优先复用已保存回执，必要时从 result snapshot 补回 linkage，并由 Contract Harness 比较 HTTP、Artifact、history 和重启入口。以后新增持久化证据不能只看即时响应，必须覆盖“CAS 行 + response payload + result snapshot”三种 replay 来源。

## M184：SQLite Action Receipt replay 可能丢失执行时间线

### 现象

首次 HTTP/Service 响应和 Artifact 已显示 Action Receipt 的 action timeline，但多 worker 并发时，第二个请求在 CAS 完成后按同一幂等键 replay，只返回 Action Receipt，没有执行时间线。

### 根因

`_complete_action_receipt()` 原来只在 `complete_interaction()` 写入 SQLite `response_payload` 之后，才给即时响应附加 `execution_timeline`。因此 CAS 行保存的最小响应没有 timeline，replay 优先读取该 payload 时无法重新构建原始计划/步骤/生命周期上下文。

### 处理与预防

将 Action Receipt 附加到即时响应后，先通过统一 `attach_action_receipt_timeline()` 刷新 top-level 和嵌套 result，再把同一有界 projection 写入 SQLite `response_payload`；Artifact、history 和 async evidence 复用同一 projection。以后新增 transition evidence 时，必须在持久化 CAS payload 之前完成公共投影，并测试“并发请求 → in-progress 暂态 → 同幂等键 replay”链路，不能只验证首次响应。

## M185：Action Preconditions 在跨入口重新推导时发生证据漂移

### 现象

M185 初版已经把 Action Preconditions 接入 Result Contract、执行时间线、异步 evidence 和 Console，但同一个完成动作在即时 HTTP response、SQLite detail/replay 和 Artifact 中可能分别显示为 `unavailable`、`not_observed` 和 `degraded`。这会让用户无法判断动作究竟是否具备执行条件，也破坏跨入口 evidence equality。

### 根因

前置条件只作为结果或 transport projection 被临时推导，没有写入规范化 Action Receipt。即时响应读取 source run，SQLite 可能只保存 CAS 的最小 response payload，Artifact 又从最终 result contract 重新推导；三者的输入层级和时机不同，因而得到不同状态。旧 Receipt replay 还不会从已保存的 bounded response 中补回该字段。

### 处理与预防

将有界的 `spatial-agent.action-precondition.v1` projection 写入 Action Receipt，且必须在 SQLite `response_payload` 完成前写入。`execution_timeline`、Result Contract、async evidence、Artifact attach、SQLite replay 和 Console 优先读取 Receipt 中的 canonical preconditions；没有该字段的旧 Receipt 才走兼容推导。回放时同时复制已保存的 preconditions，并对未知 schema 安全降级，不解释未知字段。以后新增 transition evidence，必须先确定唯一持久化来源，再覆盖即时响应、SQLite、Artifact、异步、多 worker 和重启 replay 的 equality 测试，不能让各入口分别重新推导。

## M186：强制前置条件不能误伤安全退出动作

### 现象

将 `enforce=true` 的前置条件接入生命周期 `allowed_actions` 后，最初的专项测试把 `reject` 也当成应被移除的执行动作。这样会在确认条件阻断时同时隐藏拒绝和取消，用户可能被锁在待确认状态。

### 根因

“动作需要满足数据条件”和“动作是否改变/继续执行任务”不是同一类语义。`approve`、`repair`、`retry`、`recover` 等动作会继续执行或恢复工作流，`reject` 与 `cancel` 是安全控制出口，不应被数据 readiness 或 alignment 条件阻断。

### 处理与预防

生命周期只对显式 gated execution/recovery actions 应用 enforced preconditions，`reject` 和 `cancel` 保留为安全退出路径，并将被阻断动作单独投影为 `blocked_actions`。以后新增动作必须先分类为执行、恢复、确认或安全退出，再决定是否受前置条件影响；测试必须覆盖“执行动作被阻断、拒绝/取消仍可用、未知 schema 不阻断”三种情况。

## M187：动作 lineage 测试不能复用默认持久化库

### 现象

新增 Service → SQLite/detail → Artifact 的 `transition_lineage` 验收时，使用固定幂等键的测试偶发报告“action idempotency key conflicts with a previous input”，而代码和临时 Artifact 目录都是新的。

### 根因

测试只为 Artifact 创建了临时目录，却让 `AgentService` 使用默认 state DB。默认 SQLite 会保留其他测试或本地运行的 interaction receipt，固定幂等键因此跨测试污染；这不是 CAS 或 lineage 逻辑的失败。

### 处理与预防

Service 集成测试同时为 `state_db_path` 和 ArtifactStore 使用同一临时目录，测试结束显式调用 `close()`。以后凡是验证幂等、Action Receipt、重启或多 worker 的测试，都必须显式隔离 SQLite/Artifact 根目录，不能只隔离文件输出目录；固定幂等键只允许在测试私有存储中使用。

## M188：完成动作时旧 Action Effect 覆盖了当前结果可用性

### 现象

取消一个等待确认的运行后，Service response、detail 和 Artifact 中的 Action Receipt 都显示 `state=completed`，但 `effect.result_available` 仍为 `false`；此时 Action Receipt 实际已经有 `result_run_id`。

### 根因

动作预留阶段已经生成了一个 schema v1 的处理中/无结果 Effect。完成阶段虽然写入了最终 `status` 和 `result_run_id`，但 Service 从源运行快照生成 `identity_payload` 时，嵌套 `result.action_effect` 仍是旧的结果契约投影。`project_action_effect()` 为保持已持久化 canonical Effect 的读取语义，会优先采用这个旧值，于是没有读取当前 receipt 的最终结果引用。

### 处理与预防

在 `_complete_action_receipt()` 的 canonical completion seam 中，清除顶层和嵌套 result 的旧 `action_effect`，只用当前完成后的 Action Receipt、状态和结果引用重新计算 Effect，再写入 Receipt、SQLite、Artifact 和 timeline。以后新增 transition evidence 时，必须区分“源运行的历史结果投影”和“当前动作完成投影”，完成阶段不能让旧嵌套 projection 短路新的状态。

## M188：Console bootstrap ready 早于历史恢复完成导致浏览器确认结果被覆盖

### 现象

Chrome/CDP smoke 的 preview fingerprint 与提交 fingerprint 一致，最终请求也已完成，但脚本偶发读取到不同的 final fingerprint。直接 HTTP preview→submit→resolve 链路稳定通过。

### 根因

Console 初始化 Promise 在调用异步 `restoreSession()` 之前就设置 `window.__consoleBootstrapReady=true`。浏览器 smoke 看到 ready 后立即开始新任务，而历史恢复可能稍后完成并调用 `renderRun()`，覆盖 `lastRunData`；页面状态显示的是新任务，脚本读取的 fingerprint 却来自旧历史运行。这是初始化时序竞态，不是 Planner 重新规划。

### 处理与预防

将 bootstrap ready 延后到 `await restoreSession()` 完成之后；异常路径仍设置 ready，避免服务不可用时页面永久等待。浏览器 smoke 必须等待该 ready 标记后再开始交互，并同时断言 preview、submit、complete 三阶段 fingerprint、状态、Artifact 和页面模块加载。

## M190：开放式能力候选过多导致 workflow selection 被上下文预算省略

### 现象

M190 首次接入未匹配请求的候选能力卡片后，Discovery Guidance 本身生成成功，但 Planner context 超过默认预算。`ContextBuilder` 为保留请求和工具基础信息，按顺序将 `workflow_selection` 标记为 omitted，最终 plan evidence 无法携带建议能力卡片；运行没有报错，但前端和模型看不到下一步选择。

### 根因

同一批候选卡片同时出现在 `capability_discovery`、`workflow_selection` 和 `capability_catalog`，每张卡片还包含描述、结果类型和数据可用性。上下文压缩没有识别“候选能力是开放式澄清的必要信息”，因此先省略了 workflow selection。

### 处理与预防

Runtime 给 Planner context 的候选建议限制为 4 项，保留 bounded label、input facts、result type 和 availability；完整结构化投影仍保存在 discovery/workflow selection 中供 Result、Artifact 和 Console 使用。以后扩展开放式上下文时，应区分 Planner 所需的最小候选摘要与跨入口持久化证据，并对 `context_evidence.truncated` 和关键 selection section 同时做断言，不能只检查请求最终是否返回。

## M190-D：LLM provider 失败被降级为普通执行错误，且原始响应可能进入结果

### 现象

真实模型请求发生超时、鉴权失败或中转网关错误时，LLM Planner 只抛出普通 `PlanningError`。Runtime 无法从异常本身得到稳定的 provider 分类，可能把规划阶段故障归为普通执行错误；HTTP 错误响应正文还可能被拼入 `error`，进而进入 Artifact 或历史结果。

### 根因

工具 provider 已通过 `ToolError(category/code/retryable)` 传递机器语义，但 Planner 的 `PlanningError` 没有同等元数据。OpenAI 兼容客户端只在内存 metrics 中记录 `error_type` 和 HTTP 状态，Runtime 的失败投影只能依赖人类可读错误文本猜测阶段与类别。

### 处理与预防

为 `PlanningError` 增加有界 `category/code/retryable` 元数据；OpenAI 兼容客户端将暂态 HTTP、鉴权、限流、网络、超时和无效模型响应映射到稳定语义，401/403 不重试，暂态和超时保留可重试标记。HTTP provider 正文不再写入运行错误，只保留状态类别和 versioned failure evidence。规划失败且没有候选计划时统一标记 `phase=planning`。以后新增 Planner/provider 时必须同时验证异常元数据、Runtime failure、planner metrics、Artifact、异步和 SQLite 重启，不得从原始错误文本推断核心分类或持久化 provider 响应。

## M191：结构化缺失事实未被 Runtime 生命周期门控

### 现象

Domain 已返回 `workflow_selection.state=clarification` 和 `missing_fields`，但 Runtime 只把 `ambiguous` 视为必须暂停的选择状态。规则 Planner 仍可能在事实不完整时直接生成并执行计划；同时 `provide_facts` 要求客户端重复提交完整 workflow，前端无法只提交 capability ID 和新增事实继续任务。

### 根因

能力发现、选择证据和 Runtime 门控之间缺少统一的事实状态转换。Service 的交互处理只在有 workflow payload 时合并 facts，没有复用 Domain 的 `resolve_capability_selection` 来恢复 canonical workflow；Runtime 也没有把 Domain 声明的 `missing_fields` 转换为统一 `NEEDS_CLARIFICATION` 生命周期。

### 处理与预防

Runtime 现在在无显式 workflow 时对 `clarification + missing_fields` 生成结构化澄清并停止工具执行；Service 增加 bounded capability ID 解析和统一 capability-to-workflow seam，`provide_facts` 可从已选/唯一候选能力恢复 workflow 后再合并 facts，旧的完整 workflow payload 仍兼容。以后 Domain 只声明事实和解析能力，不能让前端拼装 Domain workflow；测试必须覆盖“缺事实不执行、补事实后继续、HTTP/Artifact/SQLite 重启一致”。

## M192-A：Action Receipt 只保存目标身份，无法证明选择过渡的源/目标关系

### 现象

能力选择或补事实会从一个 `NEEDS_CLARIFICATION` 源运行创建新的计划结果。原有 `identity_linkage` 能证明 Receipt 关联了目标结果，却不能证明源运行的 Request/Plan/Evidence 身份；跨入口只能看到 source/result run ID，无法判断两者是否是同一次交互的合法过渡。

### 根因

Action Receipt 的既有 identity contract 为兼容取消、重试等动作只设计了单个目标投影，selection transition 的源运行身份在 SQLite CAS 行和结果快照之间没有独立的版本化字段。若在各入口临时从 run ID 重新读取并推导，重启、Artifact-only recovery 和 replay 会出现证据时机差异。

### 处理与预防

新增领域无关 `spatial-agent.action-transition-identity.v1`，在不改变旧 `identity_linkage` 和默认 Result equality 的前提下保存 bounded `source`/`result` Request/Plan/Result/Evidence identities。Action Receipt、execution timeline、Artifact、SQLite replay 和 Contract Harness 统一读取该 projection；未知版本安全降级为 unavailable。以后新增跨运行过渡证据必须明确 source/target 的唯一持久化来源，并覆盖首次响应、HTTP、Artifact、history、异步和重启 replay，不能只凭 transport ID 建立关联。

## M192-B：补充事实未进入通用 LLM Planner 提示

### 现象

selection → provide_facts 的规则路径可以继续运行，但真实模型路径在补充事实后仍返回 `NEEDS_CLARIFICATION`。Text Domain 的 `source` 事实已经合并进 workflow constraints，模型却继续认为没有可摘要文本。

### 根因

`workflow_request_hint()` 只渲染了少量 GIS 约束（行政区、数据集、坡度等），没有把 Domain 自定义的 workflow constraints 传给 LLM Planner。这样事实合并虽然在 Service/Runtime 内部成功，模型看到的用户提示仍然缺少新事实，形成“状态已补齐、模型上下文未补齐”的边界漂移。

### 处理与预防

增加通用、有界的自定义约束摘要：允许安全键和值进入 Planner 提示，限制长度和数组规模，并跳过 password、secret、token、credential、api_key 等敏感键。该逻辑不解释 Text 或 GIS 语义，由 workflow contract 统一承载；同时增加显式 live selection → facts → run 验收。以后新增 Domain fact 时，必须验证事实同时出现在 canonical workflow、Planner context、计划参数和跨入口结果中，不能只检查 Service 内部合并结果。
## M193-A：Evidence Revalidation 接入完成阶段时的 receipt 初始化顺序

### 现象

将 evidence revalidation 接入 Action Receipt 的完成路径时，部分失败或恢复分支会在 receipt 尚未完成初始化前读取 `receipt`，触发 `NameError`。该问题只在特定生命周期动作进入完成或异常收口分支时出现，普通规划和工具执行路径不一定复现。

### 根因

Evidence Transition、Action Preconditions 和 Action Receipt 原本分别在不同阶段投影。接入 revalidation 时把新的前置条件计算提前到了 receipt canonical projection 之前，隐含依赖了尚未建立的局部变量；同时没有明确区分预留阶段的 receipt 和完成阶段的 receipt。

### 处理与预防

完成路径现在先确保 receipt 由预留结果或安全空态建立，再按“transition evidence → evidence revalidation → action preconditions → receipt/timeline 持久化”的顺序生成 canonical projection。所有失败、取消、重试和恢复分支都复用同一顺序；未知或缺失 evidence 只投影为 `unavailable`，不抛出变量错误。以后扩展 Action Receipt 时，必须为预留、完成、失败和 replay 分别覆盖初始化状态，并通过公共 Contract Harness 验证响应、Artifact、Timeline 和 SQLite replay 的一致性。

## M193-B：新增 evidence binding 时遗漏 projection import

### 现象

首个 M193-B 预览指纹切片接入后，Text Domain 的 preview 在计划生成成功后仍返回 `FAILED`，错误为 `name 'project_transition_evidence' is not defined`。原有 M193-A 专项并未覆盖新的 preview binding 路径。

### 根因

`evidence_revalidation` 模块原先只需要规范化已生成的 transition evidence，因此只导入了 `normalize_transition_evidence`。新增 `build_evidence_binding()` 后需要从任意 Planner context 生成 projection，却遗漏了对应的 `project_transition_evidence` import；错误发生在统一 plan evidence 收口处，容易被误判为 Planner 或 Domain 失败。

### 处理与预防

补齐 projection import，并在 Docker 中用 preview→run 的公共 Service 测试覆盖“指纹匹配继续执行、指纹变化在 dispatch 前阻断”两条路径。以后新增 evidence projection 函数时，必须同时覆盖：模块直接调用、Runtime preview、Runtime run、未知/缺失证据降级，以及 HTTP/异步持久化投影；不能只验证纯函数。

## M193-C：Console 历史恢复超过浏览器 smoke 的启动窗口

### 现象

当 Console 的 SQLite 历史记录较多时，页面虽然已经加载了业务脚本，但 `restoreSession()` 仍在恢复历史运行和 artifact。原浏览器 smoke 只等待约 20 秒，因此误报“Console 页面脚本未就绪”；直接访问页面和 HTTP 接口均正常。

### 根因

`__consoleBootstrapReady` 被设计为等待历史恢复完成后才置为 `true`，这是为了避免新任务被旧历史渲染覆盖。浏览器验收脚本仍使用固定的短等待窗口，没有把“页面已加载”和“历史恢复完成”区分开，随着历史数据量增长出现了测试时序假失败。

### 处理与预防

将选择交互浏览器 smoke 的有界等待从约 20 秒调整为 60 秒，并保留 `__consoleBootstrapReady` 作为唯一就绪条件；本次实际恢复约 22.5 秒，之后 preview、confirmation、complete 和 fingerprint equality 全部通过。以后浏览器 smoke 必须等待 bootstrap ready，而不是只等待 DOM 或固定短延迟；若恢复耗时继续增长，应优化历史恢复或增加明确的恢复进度/超时证据，不能提前放宽为无界等待。

## M194-A：组合工作流误用单模板执行策略

### 现象

组合 `admin_boundary_query` 与 `raster_metadata` 时，模板编译器和 Domain Planner 已生成带命名空间的三步 DAG，但 Service preview 仍失败，错误为 `domain workflow policy rejected tools: get_raster_metadata`。

### 根因

组合计划的输出类型暂时复用了 `spatial_analysis_result`，GIS `plan_policy` 和 `validate_plan` 因此只按单个 `spatial_analysis` 模板读取 allowlist。公共组合编译器已经合并了组件，但 Domain 策略投影没有同步表达组件模板的工具并集和总步数预算。

### 处理与预防

GIS Domain 现在从组合输出中的 `component_template_ids` 和显式 workflow components 计算 allowlist 并集、组件总 max steps、required constraints 和组合 policy ID；Runtime 仍只调用 Domain policy seam，ToolRegistry 仍是唯一 dispatch 边界。以后新增组合结果类型或组件策略时，必须同时验证“编译 DAG、Domain policy、Runtime plan validation、preview/HTTP/artifact”一致，不能仅验证模板编译器的纯函数。
