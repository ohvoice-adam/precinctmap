#!/usr/bin/env bash
# CI-style gate: every Python and web check must pass. Run from anywhere.
set -euo pipefail
cd "$(dirname "$0")/.."
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0

echo "== python: ruff"
uv run ruff check .
uv run ruff format --check .
echo "== python: file/function size"
uv run python scripts/check_sizes.py
echo "== python: mypy"
uv run mypy
echo "== python: pytest"
uv run pytest -m "not bq" -q

echo "== web: install"
cd app/web
corepack pnpm install --frozen-lockfile --silent
echo "== web: tsc"
corepack pnpm typecheck
echo "== web: eslint"
corepack pnpm lint
echo "== web: vitest"
corepack pnpm test
echo "== web: build"
corepack pnpm build >/dev/null

echo "All checks passed."
