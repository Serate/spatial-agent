# M298 默认 Agent 模式与阶段可见性规格

## 1. 背景

当前 Runtime 已具备 Planner、能力目录、TaskPlan、ToolRegistry、结果契约、证据和恢复机制，但产品入口的默认值仍主要是 `rule + memory`。前端虽然预选“真实大模型 + 本地适配器”，后端默认链路没有继承这个选择；执行阶段也只在结果返回后通过高级结果区域间接展示。

因此用户的默认体验更像“调用一个固定查询”，而不是“Agent 发现能力、理解请求、生成计划、执行并汇总结果”。本阶段只接通已有能力，不新增领域策略或第二套生命周期。

## 2. 目标

在产品边界形成一致的默认 Agent 模式：

1. CLI、FastAPI 和标准库 HTTP 入口在没有显式选择时使用 `openai + local`。
2. `SPATIAL_AGENT_DEFAULT_PLANNER` 和 `SPATIAL_AGENT_DEFAULT_BACKEND` 只允许覆盖到已注册的安全选项；非法环境变量回退到产品默认值。
3. 显式传入 `rule + memory` 仍保持原语义，供离线 smoke、单元测试和无网络验收使用。
4. Composite Planner 生成的每个组件继承顶层 planner/backend，经过同一 canonical request、TaskPlan 和 execution binding 门禁。
5. 前端在请求处理期间默认显示简洁的 Agent 阶段：发现能力、理解请求、生成计划、执行任务、汇总结果；不显示 prompt、模型原文或思维链。
6. 计划、证据、工具步骤、模型指标等详细内容继续按需展开，不挤占主要回答区域。

## 3. 产品默认选择契约

### 3.1 默认值

| 配置 | 默认值 | 可用覆盖值 |
| --- | --- | --- |
| planner | `openai` | `openai`、`rule` |
| backend | `local` | `local`、`memory` |

环境变量只改变“缺省选择”，不能覆盖请求中明确传入的值。空值和非法环境变量不能导致任意字符串进入 Runtime。

### 3.2 边界

- 默认配置模块属于公共 Runtime/application 支撑层，不引用 GIS、Economic 或任何具体数据集。
- 默认值不根据 API key 是否存在而静默切换到规则规划器；真实模型未配置时应由现有健康检查或错误契约明确提示。
- `AgentService` 的低层显式参数和既有测试替身不被强制改成联网调用；产品入口负责注入默认选择。

## 4. Composite 继承语义

顶层产品选择是一次请求的运行时选择。Planner 输出没有权限声明新的 planner/backend；应用层在 canonical request 进入 TaskPlan bridge 前，将顶层选择写入全部组件。组件随后通过现有 Domain Service、ToolRegistry、TaskPlan 和 execution binding 执行。

组件集合、能力身份、工具 allowlist、结果类型和 binding fingerprint 的校验规则保持不变。继承只解决运行时选择不一致，不放宽 schema、权限、数据事实或失败状态。

## 5. 前端可见性契约

前端主结果区显示一条紧凑的 Agent 阶段条，并随状态更新：

1. 发现能力
2. 理解请求
3. 生成计划
4. 执行任务
5. 汇总结果

初始状态也显示该条但不伪造已完成状态。`QUEUED`、`PLANNING`、`EXECUTING` 和终态均由结构化状态投影驱动。高级详情默认折叠；阶段条只展示状态标签，不展示内部推理过程。

## 6. 非目标

- 不重写 Agent Runtime、Planner、ToolRegistry 或生命周期。
- 不把真实模型调用强行加入离线默认测试。
- 不为洪山区、某一个问句或某个 Domain 增加专用分支。
- 不增加自动重试次数，不保存或展示模型原文。

## 7. 验收标准

1. 缺少 planner/backend 的产品入口请求可观察到 `openai + local` 的运行时选择；显式 `rule + memory` 仍可完成离线请求。
2. Composite 规划的两个以上组件均继承顶层选择，canonical request 和 execution binding 中的选择一致。
3. 默认打开前端并提交请求时，Agent 阶段条可见且在排队、规划、执行、完成/失败时更新。
4. 详细计划、证据和轨迹默认不展开，但不丢失，仍可按需查看。
5. 配置回归、Composite 继承回归、前端 projection smoke、Docker compileall 和 architecture strict 通过。

