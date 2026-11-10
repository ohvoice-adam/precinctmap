# Contributing

Thanks for helping. This guide is for people. `CLAUDE.md` holds the same rules written for an AI assistant, and it has more detail on the data model and geography decisions.

The app is a thin layer over a library. All data logic (ingest, boundaries, aggregation, allocation) lives in `src/precinctmap/`. The API (`app/api/`) and the web client (`app/web/`) never reimplement joins or allocation.

## Set up

You need Linux or macOS (WSL2 works), [uv](https://docs.astral.sh/uv/), Node 22 or newer, and optionally Docker.

```bash
uv sync                          # Python 3.12 and dependencies into .venv
cp .env.example .env             # set PRECINCTMAP_ADMIN_PASSWORD (12+ characters) to use /admin
cd app/web && corepack pnpm install && cd ../..   # pnpm is pinned in package.json; corepack runs it
```

Run it:

```bash
uv run precinctmap serve --reload   # API on http://127.0.0.1:8000
cd app/web && corepack pnpm dev     # web client on http://localhost:5173, proxies /api
docker compose up --build           # or the whole stack in one container
```

The map is empty until boundaries and elections are loaded, and the repository doesn't ship the data. Start from a published data release with `scripts/update-data.sh` (see the README), or load your own: `uv run precinctmap boundaries load`, then `uv run precinctmap ingest <file> --review`. You can work on most code and run all tests without any data, because tests use small synthetic fixtures.

DuckDB allows one writer. While the API is running, command-line tools that open the store stop with a "store is open in another process" message. Stop the API or use the admin page.

## Run the checks

```bash
scripts/check.sh
```

This is the same gate CI runs on every pull request: ruff (lint and format), a file and function size check, mypy, pytest (BigQuery tests skipped), then tsc, eslint, vitest and the web build. Run it before you push. Quality gates to keep in mind:

- No file over 300 lines and no function over 50 lines (`scripts/check_sizes.py` enforces it). Split instead.
- Python is typed (`mypy --strict` on `src/` and `app/api/`). Public functions say what units, CRS and election date they assume.
- Every test asserts something specific. "It loads" isn't a test.
- Web dependencies are pinned to releases at least two weeks old (pnpm's minimum release age is on). Don't relax it.

The golden tests in `tests/golden/` compare the store with the Board of Elections' certified county totals. They skip when there is no local store, so CI doesn't run them. If you have a store and a change moves a golden number, stop and explain why in the pull request before updating it.

## Adding an election-results adapter

A new spreadsheet layout is the most likely outside contribution. The rules:

1. **Start from a real file.** Results layouts differ by year, and an adapter is written from a real sample, never from a guess. If you don't have one, open an issue and say which election and file you need.
2. **One adapter per layout and vintage.** When a format changes, add a new adapter (for example `fcboe_wide_2026`) instead of adding branches to an old one. Reuse shared code in `src/precinctmap/ingest/adapters/_fcboe.py`.
3. **Fail loudly.** An adapter detects its layout from headers and cell content. Exactly one adapter may claim a file; zero or two stops the ingest with a specific error. Strip BOMs, normalize headers and precinct codes, and log every normalization. Never drop rows silently.

To add one:

- Create `src/precinctmap/ingest/adapters/<name>.py` with `NAME`, `VERSION`, `detect(grid)` and `parse(grid)`. `fcboe_wide_2023.py` is a short, complete example: it builds on the 2025 layout and changes only what differs. Its docstring names the sample file and lists how the layout differs.
- Register it in `src/precinctmap/ingest/detect.py`. Single-sheet grids go in `ADAPTERS`; multi-sheet or merged-cell layouts go in `WORKBOOK_ADAPTERS`.
- Add `tests/ingest/test_<name>.py` with a fixture test and a malformed-input test. Fixtures are tiny and synthetic, built with `tests/fixtures/builders.py`. Never commit a real results file.
- Check the real file with `uv run precinctmap ingest <file> --review`. The review report must show the right election, contests and choices, a precinct match rate against the boundary set, and county-total rows that reconcile. If an election date isn't recognized, add it to `src/precinctmap/catalog/calendar.py`.
- Update the adapter lists in `CLAUDE.md`, and the layout notes in the README if users would notice.

## Data and what must never be committed

- `data/` is gitignored. It holds the database, results files (`data/samples/`, `data/raw/`), boundary files, staging and uploads. Put your real sample files in `data/samples/`; they stay on your machine. Results data is public, but it still doesn't go in git.
- **Never commit** `.env`, passwords, API keys or tokens, and never write them into source. Use environment variables. Google Cloud access uses Application Default Credentials.
- **Never commit voter or property records.** The voter file is read only as a de-identified address-to-precinct table, and names, voter IDs and birth dates are never read, stored or logged. Parcel owner names and mailing addresses are dropped when read. Test fixtures are synthetic.
- Never edit a migration that has been applied (`src/precinctmap/catalog/migrations/`). Add a new one.

## Pull requests

- Keep each one small and focused, and say what changed and what you found in the data.
- Rule of thumb for election data: every number shown must trace to a source file, and totals must reconcile after aggregation. Don't change the allocation method or tolerances without discussing it in an issue first.
- Use sentence case in the interface, and keep the map nonpartisan: colorblind-safe palettes, never party red or blue.

By contributing you agree that your work is released under the MIT license (`LICENSE`).
