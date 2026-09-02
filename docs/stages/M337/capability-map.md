# M337 Capability Map：兼容模块分类防回归

| 模块 | 职责 | 依赖 |
|---|---|---|
| classification-manifest | 维护公共模块、兼容 shim 和兼容 facade 的显式分类 | 架构守卫 |
| public-module-guard | 校验公共模块存在且不会进入兼容豁免集合 | classification-manifest |
| shim-shape-guard | 校验 shim 只包含文档、导入和安全的 `__all__` 声明，不悄悄重新承载业务实现 | classification-manifest、AST |
| architecture-report | 输出稳定 schema、错误码、分类清单和规模指标 | public-module-guard、shim-shape-guard |
| compact-contract | 验证分类边界和异常报告，作为紧凑架构回归的一部分 | architecture-report |

构建顺序：`classification-manifest` → `public-module-guard` → `shim-shape-guard` → `architecture-report` → `compact-contract`。

本阶段只治理分类事实和门禁，不移动生产模块、不删除兼容入口，也不把真实公共模块重新塞入兼容豁免。
