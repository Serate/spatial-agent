# M287 有界 Planner 修复与失败恢复 Plan

## 实施顺序

1. **A 全局规划**：完成能力图/Spec/Plan，冻结错误码白名单、Repair Request/Lineage 和生命周期边界。
2. **B Repair contract**：在领域中立 Planner seam 建立有界 request/lineage 校验，不让未知错误进入 repair。
3. **C Provider/Application adapter**：让真实/回放 Planner 接收安全 repair 指令，最多调用一次；修复后复用同一 normalize/TaskPlan bridge。
4. **D 跨入口恢复与体验**：同步 planner evidence、async/artifact/restart 和通用前端阶段投影；确保不会创建重复 run。
5. **E 阶段验收与交付**：集中运行少量 contract、Docker 门禁和一次显式 live，更新中文记录并推送版本。

## 测试节奏

- 开发中只运行当前独立失败模式的最小导入/contract 检查。
- B～D 完成后统一执行一个 M287 contract 文件，并联合 M286 相邻契约；不按每个子任务重复跑全量。
- 阶段末执行 compileall、architecture strict、readiness 和一次真实模型修复 probe；默认 CI 不联网。

## 风险控制

- 修复循环：应用层硬限制 `max_attempts=1`，不接受 provider 自己声明的更大次数。
- 安全边界：repair 不能新增 Domain、capability、tool、dataset 或权限。
- 事实一致：repair 只修改计划结构，不修改 RequestFacts、数据 readiness 或结果事实。
- 恢复一致：lineage 作为 evidence 的一部分持久化，重启后不可重复调用 provider。
