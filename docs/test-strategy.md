# Spatial Agent 测试分层策略

本项目默认测试策略从“每次跑完整矩阵”调整为“少量代表性 profile + 按需扩展矩阵”。目标是让开发反馈更快，同时保留真实 GIS、真实大模型和 Docker 生产验收的证据。

当前原则：默认入口只跑极少量代表性用例，不再按里程碑整模块执行。历史测试继续保留为专项诊断资产，但不能把 500+ 用例当成本地开发默认门禁。

## 默认门禁

### quick

日常改动默认运行：

~~~powershell
python scripts\test_profile.py --profile quick
~~~

覆盖范围：

- 3 个核心契约 tripwire：模板编译、workflow runtime 拒绝、Runtime 组合执行。

`quick` 的目标是快速发现共享契约是否断裂，不负责证明每个历史里程碑都仍完整覆盖。

### smoke

服务 smoke 与 quick 分离，按需运行：

~~~powershell
python scripts\test_profile.py --profile smoke
~~~

覆盖范围：道路坡度、DEM 元数据、澄清追问和后续回答。`scripts/smoke_check.py` 默认只跑服务 smoke，不再嵌套完整 unittest。

### stage

阶段代码收口但还未进入真实环境验收时运行：

~~~powershell
python scripts\test_profile.py --profile stage
~~~

覆盖范围是在 `quick` 基础上增加 3 个代表性离线验收场景：通用问答、复杂空间分析模板、未注册空间问题澄清。它不运行服务 smoke、不运行完整全局矩阵，也不运行脱敏模型回放。

~~~powershell
python scripts\evaluate_global.py --cases evaluation/cases/stage-acceptance.json --strict --no-model-evaluation --no-model-replay
~~~

### full-stage

只有在改动共享 Runtime、HTTP/SQLite 契约、模型评测或阶段发布前需要更强证据时运行：

~~~powershell
python scripts\test_profile.py --profile full-stage
~~~

覆盖范围：`quick + smoke + evaluation/cases/global-acceptance.json + 脱敏模型评测 + 多轮模型回放`。这是显式重型入口，不作为日常或普通阶段默认门禁。

## 真实环境验收

### gis-core

真实 GIS 核心契约只在 `spatial-agent-gis` 环境中运行：

~~~powershell
python scripts\test_profile.py --profile gis-core
~~~

该 profile 不替代完整 GIS 全量，但能快速覆盖行政区 GeoJSON、Rasterio 元数据和 analysis-ready 门控。它同样采用抽样用例，不再整模块跑真实 GIS 测试。

### live-short

真实模型默认不跑完整 live baseline。阶段验收只跑两个代表 case：

~~~powershell
python scripts\test_profile.py --profile live-short --dataset-config D:\tmp\wuhan-gis\datasets.wuhan.analysis-ready.bound.json --live-output D:\tmp\wuhan-gis\live-short.json
~~~

代表 case：

- `live-gis-spatial-overview`：覆盖空间总览、多工具 DAG、同名工具多次调用和中文答案组合。
- `live-gis-constrained-buildability`：覆盖真实 DEM/土地利用 analysis-ready、道路/水体约束、建设候选门控和工具 schema。

使用 `--dataset-config` 显式绑定 analysis-ready 配置，避免默认 raw 栅格配置触发 `grid_mismatch` 并把数据准备问题误判为模型或 Planner 问题。

### docker

Docker profile 只做 production acceptance，不在容器里默认跑完整 live baseline：

~~~powershell
python scripts\test_profile.py --profile docker --docker-base-url http://127.0.0.1:8088
~~~

容器镜像构建、完整数据卷和容器内 live baseline 只在部署或数据卷改动阶段单独执行。

## 完整矩阵

以下命令仍保留，但不是日常默认：

~~~powershell
python scripts\test_profile.py --profile full-stage
python -m unittest discover -s tests -v
python scripts\smoke_check.py --with-unit-tests
python scripts\live_baseline.py --allow-network --backend local
~~~

只有改动共享 Runtime、SQLite、HTTP 契约、生产部署、真实模型评测或数据卷配置时，才运行对应完整矩阵。即使需要完整矩阵，也应先跑失败范围最小的 profile，再按失败边界追加专项命令。

## 记录规则

- 阶段文档必须写明实际运行的是哪个 profile，而不是笼统写“测试通过”。
- live 结果只提交安全摘要，不提交 API key、本地私有配置、原始模型响应或原始 GIS 数据。
- 真实环境失败先分类为 provider、planner、tool schema、数据门控、GIS 后端或 Docker 环境，再决定是否修代码。
