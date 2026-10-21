# syntax=docker/dockerfile:1

# --- Web client build ---------------------------------------------------------
FROM node:22-slim AS web
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /web
COPY app/web/package.json app/web/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY app/web/ ./
# Optional organization name shown in the header (see .env.example).
ARG VITE_ORG_NAME=""
ENV VITE_ORG_NAME=$VITE_ORG_NAME
RUN pnpm build

# --- API + built client --------------------------------------------------------
FROM python:3.12-slim AS api
COPY --from=ghcr.io/astral-sh/uv:0.13.3 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ src/
COPY app/__init__.py app/__init__.py
COPY app/api/ app/api/
COPY config/ config/
RUN uv sync --frozen --no-dev

# Pre-install DuckDB spatial so the container never downloads extensions at runtime.
ENV PRECINCTMAP_DUCKDB_EXT_DIR=/opt/duckdb_ext
RUN .venv/bin/python -c "import duckdb; c = duckdb.connect(); \
c.execute(\"SET extension_directory='/opt/duckdb_ext'\"); c.install_extension('spatial')" \
 && chmod -R a+rX /opt/duckdb_ext

COPY --from=web /web/dist /app/static

ENV PATH=/app/.venv/bin:$PATH \
    HOME=/tmp \
    PRECINCTMAP_STATIC_DIR=/app/static \
    PRECINCTMAP_DATA_DIR=/app/data \
    PRECINCTMAP_DB_PATH=/app/data/precinctmap.duckdb

# Runs as the uid/gid compose passes (defaults to 1000 so ./data stays writable).
USER 1000:1000
# Listens on PRECINCTMAP_PORT (default 8000) on every interface inside the container; compose
# publishes it on PRECINCTMAP_HOST only.
ENV PRECINCTMAP_PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PRECINCTMAP_PORT', '8000')}/api/health\", timeout=2)"
CMD ["sh", "-c", "exec uvicorn app.api.main:app --host 0.0.0.0 --port \"${PRECINCTMAP_PORT:-8000}\""]
