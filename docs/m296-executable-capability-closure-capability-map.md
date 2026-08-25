# M296 通用能力可执行闭合与真实跨域成功链路能力图

## 阶段定位

M295 已建立“开放请求 → 能力/数据发现 → 有界澄清”的公共闭环。M296 的全局目标是把其中一个事实完整、数据可用的请求继续推进到：

```text
discovery ready
→ capability execution readiness
→ workflow / ToolRegistry / TaskPlan 闭合
→ execution binding
→ sync / async / restart / artifact 一致结果
```

GIS 与 Economic 只是两种验收载荷；公共 Runtime、Planner、ToolRegistry、生命周期、Result/View/Artifact/Evidence 不增加领域策略。

## 七维度盘点

### 产品

- 用户不需要知道工具名称，只需提供对象、目标、必要条件和期望结果。
- 当能力可用且事实完整时，用户能看到从“发现”到“执行”的连续状态，而不是停在 query-engine 式的静态匹配。
- 当能力存在但 workflow 未闭合、数据状态未知或事实不足时，系统分别给出可读、可恢复的下一步。

### 架构

- Discovery receipt 仍是唯一能力/数据发现边界；不新增第二套 Planner 或执行循环。
- execution readiness 只验证 capability → workflow → ToolRegistry schema → TaskPlan/result type 的公共闭合，最终授权仍是 M294 execution binding。
- Domain Pack 维护领域能力和数据策略，公共层只消费声明与投影。

### 数据与 GIS

- readiness 从 unknown 尽可能提升为有来源的 ready/degraded/unavailable，并保留覆盖、时间、CRS、分辨率等公共摘要。
- GIS 通用空间算子和 Economic 指标工具都通过现有注册、schema、workflow 和结果契约进入闭合链；不为洪山区、GDP 或固定问句加分支。

### 模型工程

- Rule、Replay、LLM 共享同一个 discovery/context、execution-readiness 和 TaskPlan gate。
- 真实模型只选择 catalog 中的能力；provider 失败、未知字段、未知能力和空计划继续安全澄清/拒绝。
- 不通过增加 repair 次数或放宽 schema 来制造 live 成功。

### 部署与恢复

- Docker 是 Python/GIS/compile/architecture/readiness 的默认环境；生产镜像变更后必须 build/recreate。
- 计划、binding、结果、evidence、artifact、SQLite/restart 共享 request/discovery/plan/binding identity。

### 体验

- 前端把发现、准备、计划、执行、结论和证据显示为连续阶段；只消费结构化 projection，不识别 Domain 或工具名。
- 结论优先，执行细节渐进展开；用户能区分“缺事实”“数据不可用”“能力不可执行”和“执行失败”。

### 测试与交付

- 一个完整阶段包覆盖 readiness、catalog closure、plan materialization、跨入口执行、Docker/live、前端和文档。
- 开发期间只做局部静态检查；阶段收口集中运行一个 compact contract、相邻回归和必要 Docker/HTTP/live/browser 验收。

## 不在本阶段

- 不引入 RAG、知识库问答或新的外部数据抓取平台。
- 不为了成功验收修改公共 Runtime 生命周期、绕过 ToolRegistry 或削弱 execution binding。
- 不新增大量 GIS 算子；先闭合已有通用能力。
