# M275 Plan：领域中立 Composite 结果与证据接缝

## 实施顺序

1. 新增版本化 Composite request/result/evidence 常量和有界规范化函数。
2. 新增跨 `data_profile` 的稳定并集、组件状态聚合、安全 artifact/evidence 引用和子 View 前缀隔离。
3. 通过公共 `build_result_contract` 生成标准 Result Envelope，并在 `nested_schema` 接入 Composite 专项校验。
4. 增加精简契约测试：正常混合结果、依赖环、部分失败、未知 profile、View 隔离和 evidence registry。
5. 在 Docker 中运行 M275 定向测试、compileall、architecture strict、quick/stage；不调用真实模型。
6. 更新中文恢复卡、开发问题记录和里程碑，提交并推送后从全局目标规划下一阶段的 Composite coordinator/transport。

## 设计风险与缓解

- 风险：子结果中带有宿主路径或过大嵌套数据。缓解：只通过 artifact reference 和 bounded projection 输出。
- 风险：把 Composite 类型硬编码进某个 Domain。缓解：使用局部通用 registry，公共模块不导入领域包。
- 风险：部分失败被汇总成成功。缓解：required/optional 组件和 `blocked/partial/failed` 状态显式保留。
- 风险：子 View ID 冲突。缓解：使用组件 ID 前缀并限制数量。

## Verification checkpoints

- Checkpoint A：请求规范化拒绝环依赖和越界输入。
- Checkpoint B：子结果 data profile、状态和 View 聚合稳定。
- Checkpoint C：公共 Result/Evidence nested schema 可 round-trip。
- Checkpoint D：Docker 门禁全部通过，文档与提交同步。

## Tasks

- [ ] 实现 `agent/composite_contract.py`。
- [ ] 接入 `contract_versions.py`、`evidence_registry.py`、`nested_schema.py` 和 `result_contract.py`。
- [ ] 编写 `tests/test_m275_composite_contract.py`。
- [ ] Docker 验证并记录证据。
- [ ] 更新项目记忆、问题日志和 milestones，commit/push。
