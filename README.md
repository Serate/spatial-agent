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

## 本地运行

需要 Python 3.10 或更高版本。不需要第三方依赖。

~~~powershell
python run_demo.py "查询距离主干道500米以内、坡度超过25度的区域。"
~~~

使用 OpenAI Planner：

~~~powershell
copy .env.example .env
$env:OPENAI_API_KEY="sk-your-key"
python run_demo.py --planner openai "查询距离主干道500米以内、坡度超过25度的区域。"
~~~

运行测试：

~~~powershell
python -m unittest discover -s tests -v
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
- tools/schema/tool-definitions.json：工具输入输出契约。
- evaluation/cases/m0-cases.json：评测用例。
