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
