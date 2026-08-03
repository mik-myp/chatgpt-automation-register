# GPT Auto Register

带单管理员认证的注册流水线控制台。前端使用 React、React Router、TanStack Query 和
shadcn/ui；后端使用 FastAPI、SQLAlchemy 2、Alembic，支持 SQLite 与 PostgreSQL。

## 本地开发

要求 Node.js 20+、pnpm 10+ 和 Python 3.12。

```bash
pnpm install
pnpm setup:api
pnpm dev
```

- Web：http://127.0.0.1:5173
- API：http://127.0.0.1:8000
- OpenAPI：http://127.0.0.1:8000/docs

首次启动后，从 API 日志读取 30 分钟有效的一次性初始化令牌，在 Web 初始化页创建
管理员。开发环境如需显式关闭认证，可设置
`GPT_AUTO_AUTHENTICATION_ENABLED=false`；生产环境禁止关闭认证。

API 和 Worker 是独立进程。`pnpm dev` 会同时启动前端、API 和单 Worker；API 不会在
生命周期中隐式启动 Worker。

## Docker 部署

复制根目录的 `.env.example` 为 `.env`，填写数据库密码、公开 HTTPS Origin 和 Host。
默认部署使用 PostgreSQL：

```bash
docker compose up -d
docker compose logs api
```

SQLite 轻量部署：

```bash
docker compose -f compose.sqlite.yaml up -d
docker compose -f compose.sqlite.yaml logs api
```

Compose 端口默认仅绑定 `127.0.0.1`。公网访问应由 Caddy、Nginx、Traefik 或服务器面板
终止 HTTPS，并保持 `COOKIE_SECURE=true`。PostgreSQL 与 SQLite 是独立部署，不提供跨库
复制；切换到 PostgreSQL 会创建全新数据库。

镜像包含四个入口：

```text
gpt-auto-api
gpt-auto-worker
gpt-auto-migrate
gpt-auto-cli admin reset-password [username]
```

## 数据安全

密码使用 Argon2id。Session Cookie 为 HttpOnly、SameSite=Lax，数据库仅保存 Session 和
CSRF 令牌的 SHA-256 哈希。敏感凭据使用 AES-256-GCM 加密，卡密另存 HMAC 指纹用于
去重。

主密钥默认位于持久卷 `/app/data/master.key`，权限为 `0600`。也可通过
`GPT_AUTO_MASTER_KEY_FILE` 指向 Docker Secret。数据库备份与主密钥必须分开保存；主密钥
缺失或不匹配时应用会拒绝读取敏感数据。现有 SQLite 会由 Alembic 原地加密升级，升级前
应同时备份数据库和主密钥。

## 验证命令

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm api:migrate
pnpm api:generate
pnpm --filter web e2e
```

发布 `v1.2.3` 标签会构建 `linux/amd64` 与 `linux/arm64` 镜像，并发布 `1.2.3`、`1.2`、
`1` 和 `latest` 标签，同时生成 SBOM 与构建证明。
