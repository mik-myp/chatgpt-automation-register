# 后端重构、认证、多数据库与 Docker 部署开发计划

## 1. 开发前准备

在开始 Docker 镜像发布相关开发前，需要完成以下准备：

1. 在 Docker Hub 创建公开仓库 `mikmyp/chatgpt-automation-register`。
2. 在 Docker Hub 创建具有 Read/Write 权限的 Access Token。
3. 在 GitHub 仓库 `mik-myp/chatgpt-automation-register` 的 Actions Secrets 中添加：
   - `DOCKERHUB_USERNAME`：`mikmyp`
   - `DOCKERHUB_TOKEN`：Docker Hub Access Token
4. 建议为 Docker Hub 账号启用两步验证。

Docker Hub 密码和 Access Token 不应通过聊天、代码、配置文件或 Git 提供。开发开始前只需确认 Docker Hub 仓库已创建、GitHub Secrets 已配置。

## 2. 技术决策

- 后端继续使用 Python 3.12、FastAPI、SQLAlchemy 2 和 Alembic。
- 保留按业务域组织的结构，重构大文件、全局数据库依赖以及 API/Worker 耦合。
- 仅支持 SQLite 和 PostgreSQL，不支持 MySQL，不引入 Redis。
- PostgreSQL 是默认 Docker Compose 数据库；SQLite 提供独立轻量部署文件。
- SQLite 与 PostgreSQL 是两种独立部署，不提供跨数据库数据迁移。
- 从 SQLite 切换到 PostgreSQL 时创建全新数据库，不保留 SQLite 中的任何数据。
- 所有部署模式强制登录，仅开发和测试环境允许显式关闭认证。
- 首版提供单管理员界面，但用户、角色和 Session 数据模型支持未来多用户。
- 使用一次性初始化令牌保护首次初始化。
- 敏感凭据使用 AES-256-GCM 应用层加密。
- 发布单个公开镜像，包含前端、API、Worker、迁移和 Node Sentinel 运行时。
- 正式 HTTPS 由外部 Caddy、Nginx、Traefik 或服务器面板负责。

## 3. 实施阶段

### 3.1 架构整理

- 将启动、配置、数据库、认证、业务模块、任务系统和外部协议运行时分离。
- 提供 `api`、`worker`、`migrate` 和 `cli` 四个独立入口，共用同一镜像。
- API 不再在生命周期中直接启动 Worker；Worker 通过注入的 Session Factory 工作。
- 为现有注册、邮件、短信、Kakao、Sentinel 行为添加特征测试后再拆分大文件。
- 保留业务域模块结构，禁止 router 直接操作全局数据库对象。
- 所有新增和修改文件必须使用 UTF-8 编码，不改变现有中文文本编码。

目标后端结构：

```text
gpt_auto_register/
  bootstrap/
    application.py
    lifecycle.py
  core/
    config.py
    security.py
    errors.py
  infrastructure/
    database/
    authentication/
    filesystem/
  modules/
    setup/
    auth/
    users/
    accounts/
    cards/
    pipelines/
    results/
    settings/
    kakao/
  jobs/
    models.py
    repository.py
    scheduler.py
    worker.py
  runtime/
    registration/
    account_security/
    mail/
    sms/
    fingerprint/
    sentinel/
  api/
    router.py
    dependencies.py
    middleware/
```

每个业务模块根据复杂度包含 `router.py`、`schemas.py`、`service.py`、`repository.py` 和 `models.py`，不为简单模块机械创建空层。

### 3.2 SQLite 与 PostgreSQL

- 数据库 URL 只接受 `sqlite+pysqlite` 和 `postgresql+psycopg`，其他方言启动失败。
- 将 `json_extract`、`iif` 等 SQLite 专属表达式替换为 SQLAlchemy 跨方言表达式。
- 统一 JSON、UTC 时间、连接池、事务、外键和错误处理行为。
- SQLite 使用 WAL、busy timeout 和文件级 Worker 单例锁。
- PostgreSQL 使用 advisory lock，保证首版只能运行一个 Worker。
- Alembic 在两种数据库上使用同一迁移历史，并在 CI 中分别执行升级测试。
- PostgreSQL 部署始终从空数据库执行 Alembic 初始化，不读取或导入现有 SQLite 数据。
- 不提供跨数据库 transfer CLI、全量复制、历史迁移和源目标一致性校验。
- 已选择继续使用 SQLite 的现有部署仍通过 Alembic 原地升级，不受 PostgreSQL 新部署影响。

### 3.3 初始化、认证与加密

- 增加 `users`、`user_sessions`、`setup_state`、`login_attempts` 和必要审计字段。
- 密码使用 Argon2id；Session 使用高熵随机令牌，数据库只保存 SHA-256 哈希。
- Session Cookie 设置为 HttpOnly、SameSite=Lax；生产环境要求 Secure。
- Session 默认空闲有效期为 7 天、绝对有效期为 30 天。
- 支持退出当前 Session、退出全部 Session 和修改密码。
- 所有修改请求校验 Origin 和 `X-CSRF-Token`。
- 登录失败按用户名和客户端地址限速。
- 未初始化时只开放健康检查、初始化状态、预检和初始化接口。
- 首次启动生成有效期 30 分钟的一次性令牌，只输出到日志。
- 初始化令牌过期后可通过重启重新生成，初始化成功后永久失效。
- 初始化事务同时创建管理员和完成状态，防止并发创建两个管理员。
- 提供交互式 `admin reset-password` CLI，并在重置后撤销全部 Session。
- 敏感列使用版本化 AES-GCM 密文；卡密增加 HMAC 指纹用于唯一性校验。
- 主密钥默认保存于持久卷 `/app/data/master.key`，文件权限为 `0600`。
- 支持通过 Docker Secret 文件覆盖主密钥位置。
- 主密钥缺失或不匹配时拒绝启动，数据库备份和主密钥必须分开保存。
- 现有 SQLite 数据通过一次性、可回滚的原地迁移转换为密文。
- 全新 PostgreSQL 数据库直接写入密文。
- 备份导出前在服务端解密，再沿用现有浏览器口令加密格式。
- 恢复和导出敏感数据前要求重新验证管理员密码。

### 3.4 前端与公开接口

- 增加初始化页、登录页、修改密码、Session 失效处理和受保护路由。
- Axios 默认携带 Cookie；收到 `401` 时清理本地会话并跳转登录页。
- FastAPI 直接提供构建后的前端静态资源和 SPA fallback，保持 `/api` 路径不变。
- 替换当前仅限本机中间件，改为可信 Origin、Host 和代理配置。
- 默认 Compose 端口只绑定宿主机 `127.0.0.1`，服务器通过外部反向代理访问。

新增接口：

```text
GET  /api/setup/status
GET  /api/setup/preflight
POST /api/setup/initialize
POST /api/auth/login
GET  /api/auth/session
POST /api/auth/logout
POST /api/auth/logout-all
POST /api/auth/change-password
```

除 `/api/health`、初始化接口和登录接口外，所有现有 API 强制认证。SSE、文件下载和其他长连接接口同样校验 Session。

### 3.5 Docker、Compose 与发布

- 使用多阶段 Dockerfile：pnpm 构建前端、Python 构建后端、最终镜像包含 Python 3.12 和 Node 20。
- 最终镜像以非 root 用户运行，支持 `linux/amd64` 和 `linux/arm64`。
- 默认 `compose.yaml` 包含 PostgreSQL、迁移、API 和单 Worker，应用服务使用同一镜像。
- `compose.sqlite.yaml` 使用共享数据卷运行迁移、API 和单 Worker。
- Worker 在初始化完成前只等待，不领取业务任务。
- PostgreSQL、API 均配置健康检查、启动依赖、优雅退出和持久卷。
- 首版 Compose 零配置启动：固定使用 `latest` 镜像和本机 `8000` 端口，PostgreSQL 初始
  密码为 `123456`，高级用户直接编辑 Compose。
- 首版不开放可信 Origin、可信 Host、Cookie Secure 和代理地址环境变量；生产环境固定
  同源访问，不限制使用 IP、域名或 HTTP/HTTPS 协议。
- GitHub Actions 在 `v*` 标签发布镜像。
- 发布 `v1.2.3` 时生成 `1.2.3`、`1.2`、`1` 和 `latest` 标签。
- 发布工作流生成 SBOM 和构建证明，主分支构建不覆盖正式版本标签。
- 正式发布前必须通过 lint、typecheck、单元测试、PostgreSQL 集成测试、前端测试和镜像启动测试。

## 4. 测试与验收

- 原有测试全部通过，并新增 SQLite/PostgreSQL 双数据库测试矩阵。
- 覆盖初始化并发、令牌过期、重复初始化、登录限速、CSRF、Session 撤销和密码重置。
- 验证数据库和备份中不出现敏感字段明文。
- 验证丢失或使用错误主密钥时系统安全失败。
- 验证现有 SQLite 原地升级和敏感数据加密。
- 不测试或实现 SQLite 到 PostgreSQL 的数据复制。
- 验证全新 PostgreSQL 数据库可自动迁移、初始化并写入新数据。
- 验证两套 Compose 均能完成初始化、登录、创建任务、Worker 执行、重启恢复和备份导入导出。
- 验证从 Docker Hub 拉取 `mikmyp/chatgpt-automation-register` 后无需源码即可部署。

## 5. 首版明确限制

- 不支持 MySQL。
- 不使用 Redis。
- 不支持 SQLite 与 PostgreSQL 数据互迁。
- 不支持多 Worker 或水平扩容。
- 不内置公网 HTTPS 终止服务。
- 不提供完整多用户管理界面。
- 不允许生产环境关闭认证。
