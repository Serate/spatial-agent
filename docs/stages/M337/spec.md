# Spec：M337 兼容模块分类防回归

## Objective

让架构守卫能够可靠区分三类模块：真实公共契约/引擎、只做历史转发的兼容 shim、仍包含有限适配逻辑的兼容 facade。当前版本虽然已经拆分了三类清单，但守卫只检查集合交集和文件存在，未来误分类或 shim 重新膨胀时可能仍然返回 `ok`。本阶段增加可审计的分类校验和稳定错误码。

## Scope

- 保留 `COMPAT_SHIMS`、`COMPAT_FACADES`、`PUBLIC_MODULES` 和聚合的 `COMPAT_MODULES` 兼容导出。
- 将清单改为不可变分类事实，报告中增加分类 schema 版本和逐模块分类。
- 公共模块必须存在、是 Python 文件，并且不能与任一兼容集合重叠。
- shim 必须是轻量转发模块：只允许模块文档、导入、未来导入和字符串列表形式的 `__all__`；禁止函数、类、控制流和任意运行逻辑。
- 分类异常必须以明确 `code` 出现在 `errors` 中，并在 strict 模式使报告失败。

不在本阶段做模块物理迁移、兼容入口删除、全仓测试恢复或 God module 拆分。

## Interface

`build_report()` 继续返回 `spatial-agent.architecture-check.v1`，并增加：

- `metrics.classification_schema_version`
- `metrics.module_classification`
- `errors[].code`：`public_module_missing`、`public_module_not_file`、`public_module_marked_compat`、`compat_module_missing`、`compat_shim_not_forwarder`、`compat_shim_too_large`

分类清单是架构守卫的显式输入；报告不得把一个同时出现在公共清单和兼容清单中的模块当作正常状态。

## Acceptance

1. 当前三类清单在 Docker 中通过 strict 架构检查。
2. 现有 shim 全部通过轻量转发形状检查，facade 不被误判为 shim。
3. 紧凑测试覆盖当前分类、公共/兼容交集和 shim 形状校验。
4. 人为构造缺失公共模块、公共/兼容重叠和带函数的 shim 时，报告分别返回稳定错误码。
5. 不改变 Runtime、HTTP、Domain 和 Persistence 的生产行为。

## Verification

- Docker：`python -m unittest tests.test_m262_architecture_convergence tests.test_m337_compat_classification -v`
- Docker：`python scripts/architecture_check.py --strict`
- Docker：`python -m compileall -q agent domains scripts`
- 本阶段只运行受影响的架构契约，不扩大为全量历史回归。

## Boundaries

- Always：公共模块与兼容集合互斥；shim 只保留导出转发；错误码可读且可测试。
- Ask first：删除历史 import、调整公共模块命名、改变 `architecture_check` 输出 schema。
- Never：用更新测试断言掩盖误分类；把真实引擎加入 shim；在守卫中静默忽略分类错误。
