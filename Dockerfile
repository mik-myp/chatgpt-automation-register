# syntax=docker/dockerfile:1.7
FROM node:20-bookworm-slim AS web-builder
WORKDIR /build
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json tsconfig.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/ui/package.json packages/ui/package.json
COPY apps/web apps/web
COPY packages/ui packages/ui
RUN pnpm install --frozen-lockfile
RUN pnpm --filter web build

FROM python:3.12-slim-bookworm AS python-builder
WORKDIR /build
COPY apps/api/pyproject.toml ./
COPY apps/api/src src
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GPT_AUTO_DATA_PATH=/app/data \
    GPT_AUTO_FRONTEND_DIST_PATH=/app/web
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --home-dir /app --create-home app
COPY --from=web-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=python-builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
WORKDIR /app
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/alembic ./alembic
COPY --from=web-builder /build/apps/web/dist ./web
RUN mkdir -p /app/data && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["gpt-auto-api"]
