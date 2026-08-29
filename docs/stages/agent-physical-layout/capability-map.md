# Capability Map：Agent 物理职责归类

本阶段的目标是把已经盘点清楚的职责落实到可维护的物理目录，同时保持既有公共导入、Runtime 生命周期和跨入口结果契约不变。

| Module id | 职责 | 依赖 | 首版范围 |
|---|---|---|---|
| application-support | Application 用例共享的状态、会话、格式化和异步支撑实现 | runtime contracts、persistence | 首批迁移 |
| persistence | Artifact、SQLite、Memory 的持久化实现 | runtime/result/evidence contracts | 首批迁移 |
| provider-integration | OpenAI-compatible 配置、Provider 运行能力和模型证据 | planner contracts、runtime budgets | 首批迁移 |
| result-evidence | 结果、证据、来源和答案投影 | runtime contracts、persistence | 依赖审计后迁移 |
| planning | 请求理解、能力发现、计划和工作流实现 | domain catalog、runtime contracts | 依赖审计后迁移 |
| public-seams | 稳定公共契约、兼容 facade 和顶层 Runtime/Service 入口 | 所有 canonical modules | 保留根目录，暂不机械迁移 |

## 依赖方向

```text
public-seams
    ↓
application-support ──→ persistence / provider-integration
    ↓                         ↓
runtime-core / planning ─→ result-evidence
    ↓
domains / transport adapters
```

`public-seams` 只向 canonical 实现单向委托。任何新目录都必须先有实际职责簇和至少一个生产调用方，不能为了降低根目录文件数制造浅层转发。

## 构建顺序

1. application-support
2. persistence
3. provider-integration
4. result-evidence 与 planning 的依赖审计、Spec 更新和分批迁移
5. public-seams 的最终收口与删除无引用兼容入口
