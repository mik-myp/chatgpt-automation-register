# GPT Auto Register

本地单用户注册流水线。前端使用 React、React Router、Zustand、TanStack Query 和
shadcn/ui；后端使用 FastAPI、SQLAlchemy、Alembic 和 SQLite。

项目只提供 WebUI 工作流。注册协议运行时由 API worker 在后台调用，不提供或维护
单账号命令行注册、旧版 `start_webui.py` 和旧版部署脚本等直接使用入口。

## 环境

- Node.js 20+
- pnpm 10+
- Python 3.12

## 首次安装

```bash
pnpm install
pnpm setup:api
```

## 本地开发

```bash
pnpm dev
```

- Web：http://127.0.0.1:5173
- API：http://127.0.0.1:8000
- OpenAPI：http://127.0.0.1:8000/docs

API 启动前会自动执行 Alembic migration。数据库默认保存在
`apps/api/data/gpt-auto-register.db`。SQLite 模式只允许启动一个 API Worker；第二个
API 进程会在启动阶段明确报错，避免卡密分配和任务执行产生并发冲突。

## 常用命令

```bash
pnpm lint
pnpm test
pnpm typecheck
pnpm build
pnpm api:migrate
pnpm api:generate
pnpm --filter web e2e
```

首次运行浏览器测试前执行
`pnpm --filter web exec playwright install chromium`。

修改 FastAPI 路由或 Schema 后，在 API 运行期间执行 `pnpm api:generate`，更新前端的
OpenAPI 类型和 React Query hooks。

添加 shadcn/ui 组件：

```bash
npx shadcn@latest add <component>
```

命令应在 `apps/web` 目录执行。共享组件会写入 `packages/ui/src/components`。

## 目录

```text
apps/
  api/       FastAPI、数据库模型、Alembic、后台任务与内置注册协议运行时
  web/       Vite React 应用
packages/
  ui/        shadcn/ui 共享组件
```

旧项目功能的逐项移植状态、兼容层边界和后续工作见
[`docs/migration-audit.md`](docs/migration-audit.md)。

## 安全边界

该项目明确只支持本机单用户，不包含登录、用户、角色或权限系统。开发服务固定监听
`127.0.0.1`，不要改为 `0.0.0.0` 或通过公网反向代理暴露。数据库包含邮箱凭证、Token
和卡密，应依赖本机文件权限保护。
