# Kakao 本地提取、动态代理与流水线交付说明

交付日期：2026-08-03

## 1. 交付结论

本次将 `upi-1` 作为现有第三方 Kakao 创建、查询、轮询链路的替代实现，不是扩展、备用通道或双轨运行。

- 新 Kakao 任务只使用本地引擎 `local-upi-1`，不再调用旧第三方 Kakao Base URL。
- 新任务不查询、不选择、不预留 CDK 卡密，也不再由 Worker 轮询第三方任务状态。
- 新注册任务只执行注册，不再内嵌 Kakao。Kakao 必须作为独立任务进入步骤顺序和 Kakao 任务级并发控制。
- 旧 Kakao 客户端、卡密表、卡密分配表及历史字段暂时保留，只用于兼容历史任务展示和数据读取，不参与新任务执行。
- 固定代理和旧代理池配置已从新配置模型及新任务执行路径移除。未配置代理 API 时，新任务明确失败，不允许回退到直连、固定代理或旧代理池。

`162.128.157.89:7000` 可直接使用。系统会将其标准化为 `http://162.128.157.89:7000`。也支持显式 `http://`、`https://` 和 SOCKS 地址；项目已补齐原方案需要的 `PySocks` 运行依赖。

## 2. `upi-1` 方案评估与接入

### 2.1 原方案逻辑

原方案从本地 `token.json` 提取 ChatGPT Access Token，从 `kr_proxy.json`、`vn_proxy.json` 读取代理，并按 KR -> VN -> KR 使用代理：第一、三段复用 KR，promotion 更新使用独立 VN。核心链路有九步：

1. `token_check`：KR，校验 ChatGPT Token。
2. `checkout_create`：KR，创建 KRW Kakao trial checkout。
3. `stripe_bootstrap`：KR，初始化 Stripe checkout。
4. `promotion_update`：VN，更新 promotion。
5. `provider_refresh`：KR，刷新 Stripe 状态并检查 0 KRW/Kakao Pay。
6. `taxes`：KR，同步 checkout taxes 和 Stripe tax region。
7. `payment_confirm`：KR，创建 Kakao payment method 并 confirm。
8. `approve`：KR，必要时调用 OpenAI approve。
9. `redirect_poll`：KR，轮询 Stripe redirect，最终解析 Kakao/Nicepay URL。

原始依赖为 `requests>=2.31.0`、`curl_cffi>=0.7.0`、`PySocks>=1.7.1`。当前项目已有 `requests` 和 `curl-cffi`，本次补充 `PySocks`。同步 HTTP 调用可在现有 Worker 的线程池中执行；每个线程使用独立数据库 Session，符合现有 SQLAlchemy 使用方式。

### 2.2 适配方式

没有直接执行原 CLI，也没有读取或复制其 Token、代理和状态 JSON。接入层进行了以下替换：

- Access Token 从项目 `Credential` 读取。
- KR/VN 代理由动态代理 API 按账号预分配后显式注入。
- 超时、promotion、代理国家预检由系统设置生成 workflow config。
- 原 CLI 输出改为结构化 `KakaoExtractionResult`。
- 原 stdout 日志改为持久化 `JobEvent`，并带账号和 Pipeline Item 标识。
- Worker 的取消事件传入提取引擎，九步之间及 redirect 轮询中均可停止。
- 原方案的 Seed/本地代理状态辅助代码仅为来源兼容保留；独立入口已禁用，新任务不会读取本地代理池或 Seed 状态。

### 2.3 状态与结果持久化

每个账号创建本地 `KakaoTask`，执行中和结束后保存：

- `status`、`payment_status`、`error`；
- 最终 `payment_url`；
- `checkout_session_id`、`payment_method_id`、`stripe_redirect_url`；
- `engine=local-upi-1`；
- Credential metadata 中的 Kakao 完成状态、检查时间和支付链接；
- 九步过程日志、代理预检、重试、成功、失败和跳过事件。

非 Kakao/Nicepay 域名的最终跳转不会被当作成功。账号错误被分类为不可重试；checkout 形态、代理和上游错误可按剩余预分配代理对重试。

## 3. 动态代理 API

### 3.1 请求方式

全局配置只保存一个 `代理 API 链接地址`。请求时：

- 若链接已有 `num`、`count`、`number` 或 `quantity`，覆盖其值；否则追加 `num`。
- 支持 `{count}` 占位符。
- Kakao 请求覆盖或追加 `region=KR`、`region=VN`。
- 图片 4 中的 `format`、`time`、`type=txt/json` 等其他参数原样保留。
- `Accept` 为 `application/json, text/plain`，支持纯文本、数组、嵌套 JSON 以及 `host`/`port`、`ip`/`port`、`proxy` 等常见字段。

注册和账号安全步骤对 `N` 个账号、最大尝试次数 `A`，请求 `N x A` 个代理。Kakao 的原方案必须同时具备 KR 和 VN，因此分别请求：

```text
KR 请求数量 = N x A
VN 请求数量 = N x A
Kakao API 返回槽位总数 = 2 x N x A
```

这两个区域批次组合为每次尝试的一对 `KR/VN` 代理，第三段继续复用该次 KR 代理。

### 3.2 分配和重试

API 返回位置严格保留，不会因为无效或重复代理而将后续代理向前补位。以 `A=3` 为例：

```text
账号 1：返回位置 1、2、3
账号 2：返回位置 4、5、6
账号 3：返回位置 7、8、9
```

- 同一批次先标准化，再检查格式、端口和重复地址。
- 无效或重复项占用原位置，该账号的连续分组不完整时，账号不开始执行。
- Kakao 还检查 KR/VN 批次之间及前后账号之间的重复，任一代理不得被另一个账号复用。
- 首次使用分组第一个代理；失败后严格切换下一个；成功立即停止。
- Kakao 每次尝试使用同序号的 KR/VN 代理对。
- 代理无法连接属于本次执行失败，记录原因后切换下一代理。
- 代理 API 请求失败、格式异常、数量不足、重复或无效位置都会产生明确事件。
- 只有全部尝试失败，账号才被标记为该步骤最终失败。

每次尝试事件包含：邮箱、任务步骤、尝试序号、代理地址或 KR/VN 对、结果、失败原因、开始时间、结束时间和 Pipeline Item ID。

### 3.3 旧代理机制

`registration.proxy` 和 `registration.proxy_pool` 已从配置模型和页面移除。账号安全原先按邮箱哈希选择旧代理池的逻辑已删除。新注册、账号安全和 Kakao 执行器全部使用 `ProxyAllocator`。历史 JobEvent 中的旧代理记录不会改写。

## 4. 流水线顺序与并发

### 4.1 步骤顺序

设置页展示三个步骤，并提供上移、下移按钮：

- 注册；
- 设置密码与 MFA；
- 创建 Kakao 并提取支付链接。

保存后写入 `app_settings.pipeline.step_order`。Worker 每次领取任务时按当前顺序对三类独立任务进行严格优先级调度，刷新和重启后仍保留。

这里的“顺序”是三类独立任务在队列中的调度优先级，不会自动为同一账号创建并串联三个任务。新注册任务已禁止内嵌 Kakao，避免绕过该顺序。需要完整三步时，仍需分别创建相应任务；每一步在创建和执行入口校验前置状态：

- 注册需要可领取或指定的邮箱账号。
- 设置密码与 MFA 需要 Credential，并至少有 Access Token、Session Token 或 Cookie Header 可恢复认证态。
- Kakao 需要有效邮箱、Access Token、未完成提取且没有活动 Kakao 任务。

不满足条件时记录具体原因并跳过或失败；日志区分排队、开始、步骤日志、跳过、代理重试、完成和失败。

### 4.2 两级并发

任务级并发由 Worker 的活动任务注册表和同类型领取上限控制：

- `registration_task_concurrency`；
- `account_security_task_concurrency`；
- `kakao_task_concurrency`。

达到同类型上限后任务保留在队列。不同类型可同时运行，且每种类型分别计数。

邮箱级并发由每个任务自己的 `ThreadPoolExecutor` 控制：

- 注册使用 `registration.concurrency`；
- 账号安全使用 `pipeline.account_security_email_concurrency`；
- Kakao 使用 `pipeline.kakao_email_concurrency`。

因此实际同时执行的邮箱上限为“同类型活动任务数 x 每个任务邮箱并发数”，两个上限同时生效。页面将两组配置分区展示，避免把任务数和邮箱数混淆。

## 5. 近期日志分析和修复

分析时连同 SQLite WAL 一起只读打开日志数据库。注册记录为成功 204、失败 47、取消 1，成功率约 80.95%。账号安全任务成功 3、失败 8、取消 2；历史 Kakao 状态为 done 151、failed 24。

注册失败聚类：

| 类别 | 数量 | 处理 |
| --- | ---: | --- |
| Sentinel QuickJS | 14 | 纳入 network/上游可追踪分类，保留纯 Python 回退；没有声称修复上游协议 |
| OTP timeout | 7 | 默认等待由 10 秒调整为 60 秒，仍允许 1-300 秒配置 |
| curl TLS error 35 | 5 | 归类为 network，交由账号级代理顺序重试 |
| HTTP 429 | 5 | 将 429、Too Many Requests、rate limit 纳入 network 分类和熔断统计 |
| curl timeout 28 | 4 | 归类为 network，切换下一个预分配代理 |
| HTTP 409 / invalid_state | 3 | 保留状态冲突分类和原始错误，避免无原因重试 |
| HTTP 401 | 2 | 账号/认证错误，保留明确失败原因 |
| 其他 | 7 | 保留 traceback 尾部和结构化分类 |

其他重复问题及修复：

1. `CookieConflictError` 共 3 条。原因是 Requests Cookie Jar 中多个域存在同名 `oai-did`，直接 `cookies.get(name)` 要求结果唯一。现改为遍历 Cookie Jar 按名称读取，并统一替换会触发冲突的调用点。
2. 缺认证态/凭据相关事件 5 条。账号安全执行器此前没有把保存的 Access/Session Token 传入旧运行时。现初始化 token 和 session cookie，并在执行前检查可恢复认证态。
3. Windows stderr 出现 `ModuleNotFoundError: No module named 'fcntl'`。`fcntl` 是 Unix 专用模块，现按平台条件导入；Windows 使用 `msvcrt.locking`。
4. 网络熔断阈值实现与文案不一致。现统一为连续 5 次 network 失败，并在打开熔断时记录事件。
5. 旧日志存在大量 `/api/kakao/cards/select` 和第三方 Kakao 测试接口 409。新 Kakao 创建路径不再查询卡密，设置测试改为验证 KR/VN 代理 API 返回。

### 5.1 公开参考

- Python [`fcntl`](https://docs.python.org/3/library/fcntl.html)：官方标记为 Unix 平台接口，支持 Windows 条件分支结论。
- Requests [`RequestsCookieJar`](https://requests.readthedocs.io/en/latest/api/#requests.cookies.RequestsCookieJar)：Cookie 查询可带 domain/path；本项目采用遍历 Cookie 对象避免模糊同名查询。
- Requests [Issue #3028](https://github.com/psf/requests/issues/3028) 与 [PR #3032](https://github.com/psf/requests/pull/3032)：公开复现同名多域 Cookie 导致 `CookieConflictError` 的行为。
- libcurl [错误码文档](https://curl.se/libcurl/c/libcurl-errors.html)：35 为 TLS/SSL connect error，28 为 operation timeout，支持 network 分类。
- HTTPX [代理文档](https://www.python-httpx.org/advanced/proxies/)：代理 URL 需要 scheme；因此裸 `host:port` 统一补 `http://`。
- Python [`concurrent.futures`](https://docs.python.org/3/library/concurrent.futures.html)：`ThreadPoolExecutor` 用于同步 I/O 账号并发。
- SQLAlchemy [SQLite 并发/连接池文档](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#threading-pooling-behavior)：线程执行使用独立 Session/连接，不在线程间共享 Session。
- 公开项目 [gpt-outlook-register Issue #3](https://github.com/Regert888/gpt-outlook-register/issues/3)：展示 Sentinel QuickJS/Node 环境失败及回退场景。未发现 OpenAI 对该非公开 Sentinel 流程提供稳定兼容契约或成熟通用修复。

## 6. 新增配置

| 配置 | 默认值 | 范围 | 持久化 | 生效时机 |
| --- | --- | --- | --- | --- |
| `proxy.api_url` | 空 | 有效 HTTP/HTTPS URL | `app_settings.proxy`，加密保存 | 新任务开始分配代理时；空值使新任务失败 |
| `proxy.max_attempts_per_account` | 3 | 1-10 | `app_settings.proxy` | 新任务开始分配代理时 |
| `proxy.request_timeout` | 30 秒 | 5-120 | `app_settings.proxy` | 下一次代理 API 请求 |
| `pipeline.step_order` | 注册 -> 账号安全 -> Kakao | 必须恰好包含三项且不重复 | `app_settings.pipeline` | Worker 下一次领取排队任务 |
| `pipeline.registration_task_concurrency` | 1 | 1-20 | `app_settings.pipeline` | Worker 下一次领取注册任务 |
| `pipeline.account_security_task_concurrency` | 1 | 1-20 | `app_settings.pipeline` | Worker 下一次领取账号安全任务 |
| `pipeline.kakao_task_concurrency` | 1 | 1-20 | `app_settings.pipeline` | Worker 下一次领取 Kakao 任务 |
| `registration.concurrency` | 10 | 1-50 | `app_settings.registration` | 新注册任务创建时写入快照；任务内生效 |
| `pipeline.account_security_email_concurrency` | 10 | 1-50 | `app_settings.pipeline` | 账号安全任务开始时 |
| `pipeline.kakao_email_concurrency` | 10 | 1-50 | `app_settings.pipeline` | Kakao 任务开始时 |
| `kakao.timeout` | 30 秒 | 5-300 | `app_settings.kakao` | Kakao 账号执行时 |
| `kakao.poll_timeout` | 120 秒 | 30-300 | `app_settings.kakao` | redirect 轮询开始时 |
| `kakao.verify_proxy_countries` | true | 布尔值 | `app_settings.kakao` | Kakao 代理预检时 |

运行中的账号继续使用已经预分配的代理，不因保存设置而中途换组。历史任务的代理和卡密字段保持原值。

## 7. 修改文件清单

本需求的核心实现文件：

- `apps/api/pyproject.toml`
- `apps/api/src/gpt_auto_register/modules/kakao/extractor.py`
- `apps/api/src/gpt_auto_register/modules/kakao/local_service.py`
- `apps/api/src/gpt_auto_register/modules/kakao/router.py`
- `apps/api/src/gpt_auto_register/modules/pipelines/repository.py`
- `apps/api/src/gpt_auto_register/modules/pipelines/router.py`
- `apps/api/src/gpt_auto_register/modules/pipelines/schemas.py`
- `apps/api/src/gpt_auto_register/modules/settings/router.py`
- `apps/api/src/gpt_auto_register/modules/settings/schemas.py`
- `apps/api/src/gpt_auto_register/modules/settings/service.py`
- `apps/api/src/gpt_auto_register/runtime/auth_flow.py`
- `apps/api/src/gpt_auto_register/worker/account_security_executor.py`
- `apps/api/src/gpt_auto_register/worker/executor_support.py`
- `apps/api/src/gpt_auto_register/worker/legacy_runner.py`
- `apps/api/src/gpt_auto_register/worker/manager.py`
- `apps/api/src/gpt_auto_register/worker/pipeline_executor.py`
- `apps/api/src/gpt_auto_register/worker/pipeline_kakao_executor.py`
- `apps/api/src/gpt_auto_register/worker/proxy_service.py`
- `apps/web/src/features/pipelines/components/create-kakao-dialog.tsx`
- `apps/web/src/features/pipelines/components/create-registration-dialog.tsx`
- `apps/web/src/features/pipelines/components/kakao-tasks-tab.tsx`
- `apps/web/src/features/settings/components/kakao-settings-tab.tsx`
- `apps/web/src/features/settings/components/pipeline-settings-tab.tsx`
- `apps/web/src/features/settings/components/registration-settings-tab.tsx`
- `apps/web/src/features/settings/pages/settings-page.tsx`
- `apps/web/src/components/pipelines/runtime-event-log.tsx`
- `apps/web/src/api/generated.ts`

针对性测试文件：

- `apps/api/tests/test_proxy_service.py`
- `apps/api/tests/test_worker_scheduling.py`
- `apps/api/tests/test_kakao.py`
- `apps/api/tests/test_pipeline_card_allocation.py`
- `apps/api/tests/test_pipeline_details.py`
- `apps/api/tests/test_security_settings_results.py`
- `apps/web/src/components/pipelines/runtime-event-log.test.tsx`
- `apps/web/src/pages/pipelines-page.test.tsx`

## 8. 测试和验收

已覆盖：

- 裸 `host:port` 标准化；数量/区域参数覆盖；txt/JSON 解析；顺序连续分组；重复和无效位置不补位；代理 API 未配置失败。
- Kakao KR/VN 跨区域、跨账号重复检测；本地任务详情、完成状态和支付链接持久化。
- 旧卡密容量检查不再进入新 Kakao 创建路径。
- Worker 持久化步骤顺序和同类型任务级并发上限。
- 前置 Credential/token 校验、认证态传递和运行日志展示。
- 设置页桌面与 390 x 844 移动视口；顺序保存、刷新持久化；无控件重叠；WCAG A/AA 自动检查无违规。

最终回归结果：

- 后端 Ruff：通过。
- 后端 Pytest：`104 passed`。
- 前端 TypeScript typecheck：通过。
- 前端 Vitest：`11` 个测试文件、`32 passed`。
- 前端 ESLint：通过。
- 前端 Vite production build：通过。
- `git diff --check`：通过。
- 浏览器冒烟：新建注册不再显示 Kakao 内嵌入口；动态代理、三步顺序、任务级并发和邮箱级并发页面展示正常。

## 9. 已知限制与建议

- 没有有效真实 ChatGPT Token、KR/VN 代理和可用活动资格，因此未执行真实 Kakao/Stripe 外网端到端支付链接提取；当前验证范围是 mock、结构、错误分类、代理分配和数据库持久化。不能据此声称真实上游已稳定跑通。
- Kakao 引擎依赖 ChatGPT、Stripe、Kakao/Nicepay 的非公开响应结构、Stripe runtime/version 和 promotion 资格，上游变化可能使步骤失效。建议为九步状态码和响应形态建立脱敏样本回归，并配置失败率告警。
- Sentinel QuickJS 是当前最高频单项错误，但没有稳定官方接口可依赖。临时规避是保证 Node/QuickJS 运行环境可用、保留纯 Python 回退，并按错误分类观察失败率；后续应在取得合法稳定接口或上游兼容说明后再升级实现。
- SQLite 在高任务级并发 x 高邮箱并发下仍可能遇到写竞争。当前使用独立 Session 并限制配置范围；生产高吞吐建议迁移 PostgreSQL，并基于真实代理/API容量压测后逐步提高并发。
- 步骤顺序只调度已经创建的独立任务，不自动生成下一步骤。若需要真正的账号级三步 DAG，应另行增加编排实例、步骤产物传递和失败恢复模型，而不是复用当前全局优先级。
- 旧第三方 Kakao 客户端和卡密数据结构尚未物理删除，以保证历史页面和备份兼容。确认不再需要历史明细后，可通过单独迁移版本删除代码、接口和表。
