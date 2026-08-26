# M300 开放问题 Agent 成功率与答案体验实施计划

## A：全局基线与任务事实

- 盘点开放问题在 RequestFacts、能力发现和澄清阶段的公共缺口。
- 冻结 success、clarification、data unavailable、provider failure 的状态矩阵和 fingerprint 规则。
- 只补领域中立契约，不复制 GIS/Economic 流程。

## B：受控能力组合

- 让 Planner 根据目标、事实、data profile 和 readiness 选择已登记能力。
- 验证多步 DAG、workflow、ToolRegistry、TaskPlan 和 execution binding 的闭合。
- 对未匹配、不可物化和信息不足分别返回可恢复状态。

## C：真实模型可靠性

- 复用 planner envelope 和现有 provider structured-output seam，区分超时、结构不合规和语义不可执行。
- 保留有限 repair/retry，不改变能力、权限和数据选择。
- 同步、异步、重启和 artifact 只复用统一生命周期，不建立第二套模型流程。
- provider 不可用时返回可重试的 planning failure 与有界 failure evidence；只有事实缺失才进入澄清状态。

## D：答案与前端体验

- 以结构化 Result/View/Evidence 为唯一输入，统一输出结论、关键发现、限制和下一步。
- 默认 LLM Planner 成功路径启用结构化答案生成；Rule/Replay/直接执行和未配置模型保持离线回退，并保留显式关闭开关。
- 让阶段条、澄清动作和结果卡反映真实状态；详细证据默认折叠。
- 用未知结果类型和缺失数据做通用降级，不增加专题页面分支。

## E：集中验收

- 在 Docker 真实数据上选择少量开放请求，执行 Rule/Replay 对照和一次显式 live。
- 比较同步/异步、artifact/restart、HTTP 和前端的 request/result/evidence identity。
- 集中运行 compact contract、Node smoke、compileall、architecture strict、readiness；不重复跑无关测试。

## F：交付与全局重规划

- 更新中文问题记录、任务账本、milestone 和恢复快照。
- 提交并推送阶段版本。
- 从产品、架构、数据、模型、部署、体验、测试七个维度重新确定下一阶段，不陷入数据细节。

## 依赖与风险

- 依赖：现有 planner envelope、selection evidence、execution binding、Result/View/Evidence 和 Docker GIS 数据。
- 风险：中转 provider timeout；处理为显式 provider failure，不以增加重试或放宽校验掩盖。
- 风险：上下文继续膨胀；所有新增字段必须进入有界 envelope 和投影矩阵。
- 风险：答案生成过度程序化；只扩展通用事实到答案投影，不在领域代码手写完整结论。
