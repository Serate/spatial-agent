# M337 阶段交接

## 状态

- 阶段：`M337` 兼容模块分类防回归
- 状态：M337-A～D 已完成，待提交推送阶段版本
- 协作：单 Agent，最大并发度 1；测试优先使用 Docker
- 基线：`dea1180`

## 恢复入口

只读取本文、`docs/agent-work-state.md`、`tasks/current-state.md`、M337 plan 当前子任务，以及明确列出的源码/测试文件。不要默认读取完整历史或全量测试。

## 当前任务

1. 提交 M337 阶段代码、测试和文档变更并推送阶段版本。
2. 提交后按项目全局目标重新规划下一阶段。

## 必要文件

- `scripts/architecture_check.py`
- `tests/test_m262_architecture_convergence.py`
- `tests/test_m337_compat_classification.py`
- `docs/compatibility-matrix.md`
- `docs/agent-development-issues.md`
- `docs/document-index.json`
- `docs/agent-work-state.md`
- `tasks/current-state.md`

## 禁止事项

- 不删除历史兼容 import，不移动生产模块。
- 不把公共模块加入兼容豁免，不用测试断言掩盖分类错误。
- 不提交密钥、模型原文、Prompt 或运行产物。

## 验证结果

- 本地 M337 + M262 紧凑契约 `10/10` 通过；`architecture_check.py --strict` 通过；目标文件 compileall 通过。
- Docker M337 + M262 紧凑契约 `10/10` 通过；strict 架构检查通过；`python -m compileall -q agent domains scripts` 通过。
- Docker 两个容器为 `healthy`，`/health/ready` 返回 HTTP 200。

## 待提交内容

- 架构守卫、M337 紧凑测试、阶段文档、热状态、兼容矩阵和必要问题日志。
