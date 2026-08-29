# Plan：M324 受控工具治理可见化与重启再绑定

> 顺序：全局复盘 → capability map → Spec → 实现 → 最小必要验证 → 交接 → 全局重规划。
> 单 Agent，最大并发度 1；同一阶段尽量形成完整能力切片，不按文件拆成微阶段。

## M324-A：approved binding 重启再绑定

- [x] 在 Runtime 创建 seam 接入持久化 approved record 的再绑定。
- [x] 保持 handler 只引用 sandbox identity，不从记录读取源码。
- [x] 处理 handler unavailable、duplicate binding、revoked 和版本/指纹漂移，全部 fail closed。
- [x] 增加紧凑后端回归，覆盖首次恢复、重启恢复、幂等和不可执行状态。

## M324-B：审批状态用户投影

- [x] 确认现有 `HTTPApplication` 的审批 action/response 是唯一语义来源。
- [x] 为控制台提供有界列表、状态标签、允许动作、错误和恢复状态投影。
- [x] 保持 FastAPI/stdlib 传输适配薄，增加一条跨入口核心字段对照验证。

## M324-C：Console 审批面板

- [x] 在现有结果工作区增加紧凑“工具治理”区域，默认不遮挡对话和地图。
- [x] pending 只显示批准/拒绝，approved 只显示撤销，终态显示原因，不显示源码或样例参数。
- [x] 动作完成后刷新列表并反馈状态；失败显示安全错误，不清空当前分析结果。
- [x] 增加 Node projection smoke 和资源构建验证。

## M324-D：集中验收与交付

- [x] Docker 重建后运行 M324、M323、M322 精简回归。
- [x] 运行 compileall、architecture strict、code/document index、readiness 和跨入口 HTTP smoke。
- [x] 更新 `docs/agent-work-state.md`、`tasks/current-state.md`、任务账本、中文问题日志和阶段交接。
- [x] 完成全局复盘，规划 M325 真实模型 + Docker/GIS + 网络搜索验收；真实模型调用放到 M325 显式验收。

## 收口结论

M324 已完成。approved 工具的重启再绑定、版本/指纹失配 fail-closed、HTTP 安全投影和
Console 治理面板均已接入同一 Registry 边界；未改变审批角色、沙箱网络策略或自动批准行为。

## 风险与控制

| 风险 | 控制 |
|---|---|
| 重启后误执行旧工具 | 重新读取 approval store，并由 Runtime gate 校验状态、版本和指纹 |
| sidecar 丢失源码缓存 | handler 返回 unavailable，Registry/Runtime 不绕过沙箱 |
| 前端暴露敏感字段 | 只消费 HTTP 有界 projection，Node smoke 检查禁止字段 |
| 双入口语义分叉 | 业务动作只走 `HTTPApplication`，传输层只做解析和状态码映射 |
