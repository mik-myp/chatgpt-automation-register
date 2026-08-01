# gpt-outlook-register 移植审计

审计基线：`../gpt-outlook-register`，审计日期：2026-08-02。

产品范围：只验收 WebUI 可访问的完整工作流。旧项目的独立命令行、启动器和部署脚本
不是本项目的移植目标。

## 已完成

| 旧项目能力 | 新项目位置 | 状态 |
| --- | --- | --- |
| Outlook 四段、邮件链接两段导入 | `modules/accounts` | 已完成 |
| Outlook、邮件链接、CF 临时邮箱注册 | `worker` + `runtime` | 已完成 |
| 并发注册、代理池、网络错误分类与熔断 | `worker/manager.py` | 已完成 |
| Access、Session、Refresh Token 保存 | `db/models/accounts.py` | 已完成 |
| 结果导出、CPA/Sub2API 发布、Plus 检查 | `modules/results` | 已完成 |
| SMS 平台、动态国家、号码复用 | `modules/settings` + `runtime/sms_provider.py` | 已完成 |
| Kakao 资格检查、任务创建、同步、取消、重试 | `modules/kakao` | 已完成 |
| 卡密批次、实时用量、流水线分配 | `modules/cards` | 已完成并增强 |
| 账号重置、释放、批量删除、卡死账号回收 | `modules/accounts` | 已完成 |
| 流水线暂停、恢复、取消、失败项重试 | `modules/pipelines` | 已完成并增强 |
| 旧 SQLite 账号与凭证迁移 | `cli/migrate_accounts.py` | 已完成 |

核心协议文件除 `sms_provider.py` 的适配改动外，与旧项目逐文件一致，保留在
`runtime/` 兼容层中，通过独立子进程调用，避免环境变量和动态导入污染 API 进程。

## WebUI 待优化

| 能力 | 影响 | 建议 |
| --- | --- | --- |
| SSE 日志流 | 新前端目前轮询持久化事件 | 功能可用但实时性和请求成本不同；需要时增加事件流端点 |
| 旧版运行中修改并发数 | 新版配置只影响新建流水线 | 保持快照语义；若要动态扩缩容需单独设计，不直接移植 |

## 明确不移植

- 单账号命令行 `register_outlook.py`。
- `start_webui.py` 自动安装、启动和打开浏览器流程。
- 旧版 Ubuntu systemd 安装脚本与 service 文件。
- 任何要求用户直接运行 `runtime/` 内协议脚本的使用方式。

## 维护边界

- `runtime/` 是 WebUI 后端的内部协议兼容层，不属于用户入口；以行为稳定为优先，
  不纳入新代码的 Ruff/Mypy 严格门禁。
- `worker/legacy_runner.py` 是动态导入适配器，不纳入 Mypy；其余 API、数据库、领域模块必须通过严格检查。
- 新功能应进入 `modules/<domain>` 的 router/service/repository 分层；不要继续向
  `worker/manager.py` 或 `runtime/` 添加 Web/API 领域逻辑。
- 协议运行时变更后应运行 `pnpm lint`、`pnpm typecheck`、`pnpm test`、`pnpm build`，
  并从 WebUI 发起端到端验证。
