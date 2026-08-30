# M333 阶段交接

## 状态

- 阶段：`M333` 受控公共网页模式与网页正文读取
- 状态：已完成
- 基线：`fb64824`；交付提交待生成
- 协作：单 Agent，最大并发度 1；Docker 优先，默认测试精简

## 目标与决策

在现有白名单搜索基础上增加显式 `public` HTTPS 模式和 `web_fetch`。默认保持 `allowlist`。公共模式不等于无边界公网：必须阻断 SSRF、凭据 URL、危险重定向、脚本、下载和非 HTML 文档。网页正文只服务当前 Run 的模型上下文，持久化只保存安全元数据。

## 已完成

- M333-0：capability map、Spec、Plan、handoff 已建立。
- M333-A：共享 `WebAccessPolicy`、`off/allowlist/public` 配置、DNS 地址安全检查和 `web_search` 兼容迁移已完成。
- M333-B：`WebFetchAdapter`、HTML 正文抽取、大小/类型/重定向限制和临时 `_model_context` seam 已完成。
- M333-C：`web_fetch` 已接入 Factory、通用 `document_evidence`、ReAct、答案上下文和恢复重抓；同一 Run 来源授权已收口。
- M333-D：Docker 阶段门禁、真实模型 + 真实公共 HTML 验收、文档与索引收口已完成。

## 验收结果

- 本机 M333 紧凑回归 `11/11`。
- Docker M333 + M321 + M320 紧凑回归 `43/43`；compileall、architecture strict、readiness `200` 通过。
- Docker 真实模型 + 真实公共 HTML 页面：`COMPLETED`；规划器和答案生成成功，`web_fetch` 1 步完成，网页正文临时上下文 1 份。
- 新增边界验证：答案上下文硬上限、SQLite/Artifact 正文不持久化与恢复重抓、HTTP/事件安全投影。

## 必要文件

- `agent/agent_settings.py`
- `agent/network/web_policy.py`
- `agent/network/web_search.py`
- `agent/network/web_fetch.py`
- `agent/network/__init__.py`
- `agent/runtime_factory.py`
- `agent/runtime_core/react_runtime.py`
- `agent/answer_generation.py`
- `agent/runtime_core/execution.py`
- `agent/runtime_core/decision_resume.py`
- `agent/runtime_core/recovery.py`
- `agent/persistence/sqlite_store.py`
- `agent/persistence/artifact_store.py`
- `tests/test_m333_web_public.py`
- `tasks/current-state.md`
- `docs/agent-work-state.md`

## 恢复入口

只优先读取 `docs/agent-work-state.md`、`tasks/current-state.md` 尾部、本 handoff、M333 plan 当前子任务和上面列出的必要文件；不要读取完整历史、全量测试、模型原文、网页正文或敏感配置。

## 验证与阻塞

- M333 公共策略、网页读取与 M321 搜索定向测试已通过；集成回归、Docker 和真实模型验收已完成。
- 无阻塞。真实公网和真实模型验收放在 M333-D，不能替代离线策略测试。

## 全局重规划输入

- 产品：公共网页能力已能支持“搜索来源 → 读取正文 → 通俗回答”，但搜索 Provider 仍是服务端配置项，网络不可达时必须明确降级。
- Runtime：正文临时上下文边界已闭合；下一阶段应从全局目标检查多来源上下文去重、证据新鲜度和跨 Run 恢复成本，不把网页正文持久化。
- Planner：`web_fetch` 已成为受控 ReAct 工具，但模型仍只能调用已登记工具；新增网络能力继续通过 schema、策略和 Registry。
- 数据/Domain：公共网页是 Runtime 网络能力，不属于 GIS Domain；GIS 与网页证据组合应继续走通用 Result/Composite，而不是增加专题分支。
- 部署：生产 Compose 必须显式使用 `--env-file .env.production`；代理只配置在主服务，工具提案沙箱保持无网络。
- 测试：默认保持离线精简；真实网络、真实模型和 Docker 仅作为显式验收路径。

## 阶段结束条件

M333-A～D 全部完成，默认/公共模式边界有紧凑回归，至少一条 Docker + 真实模型 + 公共 HTML 验收通过，文档索引和中文问题日志更新后提交推送。
