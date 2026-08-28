# M319 通用 Execution Policy 实施计划

## 任务包

1. **策略解析器**
   - 扩展 `execution_policy.py`，提供 `ExecutionPolicyResolver`。
   - 根据显式 workflow、Domain `plan_policy`、计划形状和可选 requested mode 解析四种模式。
   - 统一工具、结果类型、动作/轮次预算、确认、网络和工具提案开关。

2. **规划门禁**
   - `RuntimePlanningSurface.validate_plan_for_execution()` 先完成 Domain/通用校验，再
     运行解析器门禁；workflow 只在提供时调用 workflow validator。
   - 生命周期和 preview 不再把“没有 workflow”当成所有请求的前置失败。

3. **证据与重规划**
   - Runtime 的 `execution_policy` evidence 改为真正包含 v1 核心字段，同时保留
     `tools`、provider 和权限等既有治理摘要。
   - 计划修复和执行重规划后刷新 policy evidence；失败结果提供 unavailable policy。

4. **兼容检查**
   - 检查 execution-binding、异步、SQLite、artifact 和恢复读取不依赖旧 evidence 的
     治理字段；不改变 binding schema，避免无关跨入口迁移。

5. **阶段收口**
   - 新增精简 M319 测试；Docker 运行策略矩阵、compileall、architecture strict。
   - 更新 `tasks/task-progress.md`、`docs/agent-work-state.md`、`docs/agent-development-issues.md`，
     提交并推送阶段版本，然后依据全局 M320-M325 计划重规划。

## 依赖与风险

- 解析器必须保持 Domain-neutral，不能复制 GIS workflow 规则。
- 现有历史测试使用自定义结果类型；Runtime 默认不把 Registry 全量结果类型校验强加
  到无 Domain policy 的旧计划上，显式 Domain policy 仍严格校验。
- 旧消费者依赖 `execution_policy.tools`，因此 evidence 保留该字段，核心 policy 另行
  通过 allowlist 字段表达。

## 验证检查点

- P1：解析器四模式和 fail-closed 边界通过。
- P2：普通无 workflow Runtime 完成，显式 Domain workflow validator 仍被调用。
- P3：preview/replan/失败证据包含合法 policy projection。
- P4：Docker 精简门禁通过后交付版本。
