# M280 真实跨域 Composite 纵向验收能力图

## 阶段目标

把 M279 的“可规划”推进到一条真实可验收的跨域闭环：真实中转模型生成合法 Composite DAG，系统经过本地契约校验后执行 GIS + Economic 组件，并在 async、SQLite/artifact、evidence 和重启后保持一致。

```text
provider probe
  -> Composite Planner response compatibility
  -> capability/DAG/Domain allowlist
  -> M278 sync/async execution
  -> GIS + Economic Result
  -> artifact/evidence/restart comparison
```

## 分层

| 层 | 目标 | 证据 |
|---|---|---|
| Provider | 中转可达、输出可解析 | 脱敏 provider receipt |
| Planner | 输出合法组件、Domain、能力和依赖 | plan contract/repair lineage |
| Execution | GIS + Economic 真实数据执行 | composite result/components |
| Recovery | async、artifact、SQLite、restart 一致 | run/detail/observability/evidence |
| Product | 为后续动态前端提供稳定 payload | result/view/evidence contract |

## 边界

- 不把某个真实问句写成特殊分支；允许有限的 provider compatibility normalization，但最终仍必须通过 canonical schema。
- 不把 live case 放进默认 CI，不保存 prompt、模型原文、密钥、真实原始数据或宿主路径。
- 前端动态 Composite View 只做契约准备，不在本阶段重写前端布局。
