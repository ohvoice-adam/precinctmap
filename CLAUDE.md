# CLAUDE.md — precinctmap

Open-source election results toolkit and map app. Two parts in one repo:

1. **`precinctmap` library** (`src/precinctmap/`): ingests messy results spreadsheets, catalogs elections, versions precinct and other boundaries by election, and aggregates or allocates precinct results to other geographies.
2. **Results map app** (`app/`): users pick a year, election, contest, and geography (precinct, Columbus council district, municipality/township, ZIP code) and see the results mapped, with tooltips, a detail panel, and export.

The app is a thin layer over the library. All data logic lives in `src/precinctmap/`; the API and the web client never reimplement joins or allocation.

If the project is renamed, follow a checklist: the package, CLI, `PRECINCTMAP_*` settings, `X-PRECINCTMAP-Admin` header, Docker service and store file all carry the name.

## Who uses this

- **Maintainer and admin:** technical and terse. Lead with the root cause and the change, not a tutorial. When data is ambiguous, ask; don't guess.
- **App users:** staff of civic and nonpartisan organizations, mostly non-technical. The map has to be self-explanatory, and every number must be traceable to a source file.

## Environment

- Development runs in **WSL2 Ubuntu on a Windows ARM (Snapdragon) laptop**, so Linux aarch64. Prefer packages with aarch64 wheels and say so if one is missing.
- Python 3.12 via **uv** (`uv sync`, `uv run ...`). No pip, no conda.
- Node 22 LTS with **pnpm** for the web client (Docker uses `node:22`; the dev box has Node 24, which also works). pnpm is pinned in `package.json` and run through corepack. pnpm's minimum-release-age policy is on: pin web dependencies to releases at least two weeks old rather than relaxing it.
- Docker and Docker Compose are available. Production target is a Docker Compose stack on a self-hosted server reached over a private network, so no public exposure by default.
- Google Cloud auth uses Application Default Credentials. Never write keys or tokens into the repo.

## Stack

- **Library:** pandas, GeoPandas, Shapely 2, pyogrio, openpyxl/calamine for spreadsheets, DuckDB with the `spatial` extension
- **Store:** one DuckDB file (`data/precinctmap.duckdb`) holds the catalog, results, and boundaries. GeoParquet for boundary interchange.
- **Warehouse (optional sync):** BigQuery project from `GOOGLE_CLOUD_PROJECT` (set in `.env`, never committed). The app never queries BigQuery at request time.
- **API:** FastAPI + Uvicorn, Pydantic models
- **Web:** Vite + TypeScript + MapLibre GL JS. No heavy framework unless Phase 0 makes a case for one.
- **Basemap:** a no-tracking source (OpenFreeMap, or self-hosted Protomaps PMTiles). No Google or Mapbox keys.
- **Tooling:** ruff, mypy (`src/`, `app/api/`), pytest; eslint + tsc + vitest on the web side

## Commands

```bash
uv sync
scripts/check.sh                 # CI gate: ruff, mypy, pytest, tsc, eslint, vitest, build
uv run pytest                    # all Python tests
uv run pytest -m "not bq"        # skip BigQuery tests
uv run ruff check . && uv run ruff format . && uv run mypy src app/api
uv run precinctmap boundaries load [--replace <set>]  # make the store match config/boundaries.toml, build crosswalks
uv run precinctmap boundaries report                 # per election: precinct match, exact/allocated/excluded by geography
uv run precinctmap boundaries list
uv run precinctmap ingest data/samples/*.xlsx --review [--full]   # stage files, print review reports
uv run precinctmap ingest <file> --review --election-date YYYY-MM-DD  # when the name has no year
uv run precinctmap ingest <file> --review --reprocess [--certified]  # re-derive an ingested file (after corrections)
uv run precinctmap ingest --commit <staging_id>      # commit a reviewed batch (same sha256 = no-op)
uv run precinctmap catalog [--election <id>]         # list elections (or one election's contests)
uv run precinctmap aggregate run [--election <id>]   # rebuild geo_results and assert reconciliation (also runs after commit/load)
uv run precinctmap aggregate report                  # reconciliation status and village allocation check
uv run precinctmap addresses load data/samples/VOTERFILE.TXT --as-of D [--commit]   # de-identified address table
uv run precinctmap parcels review data/samples/Parcel.csv --as-of D [--reprocess]  # locate parcels, print report
uv run precinctmap parcels commit <prc-id> [--replace]                            # commit a reviewed parcel batch
uv run precinctmap parcels stats                     # rebuild area statistics (after adding a measure)
uv run precinctmap parcels status
uv run precinctmap census fetch --year 2024 --as-of D           # ACS summary-file tables, county rows only (no API key)
uv run precinctmap census load --year 2024 --as-of D [--commit] # allocate to every geography; review, then commit
uv run precinctmap census status
uv run precinctmap bundle export --out dist      # data release: every table as Parquet, source sheets, manifest + DATA.md
uv run precinctmap bundle load <archive>          # into an empty store: sha256-checked, geo_* rebuilt and re-reconciled
uv run precinctmap bundle info <archive>
uv run precinctmap serve --reload              # API on PRECINCTMAP_HOST:PRECINCTMAP_PORT (from .env; default 127.0.0.1:8000)
cd app/web && corepack pnpm dev                # web on :5173, proxies /api (pnpm pinned via packageManager)
docker compose up --build                      # full stack
```

## Layout

```
src/precinctmap/
  ingest/        # one adapter per source format/vintage; format detection; staging
  catalog/       # elections, source files, contests, choices; DuckDB schema + migrations
  registry/      # boundary sets by geography and vintage; precinct crosswalks
  aggregate/     # exact aggregation and population-weighted allocation; materialized results
  io/            # DuckDB, GeoParquet, BigQuery readers/writers
  cli.py
app/
  api/           # FastAPI: read endpoints + admin ingest endpoints
  web/           # Vite + TS + MapLibre client
tests/
  fixtures/      # tiny synthetic files only
  golden/        # outputs that reproduce previously reported numbers
data/            # gitignored: raw/, staging/, boundaries/, samples/, precinctmap.duckdb
docker-compose.yml
```

## Data model (catalog)

Long format throughout. Schema lives in `src/precinctmap/catalog/migrations/` (never edit an applied migration; add a new one).

- `elections` (election_id like `franklin-2024-11-05-general`, county, election_date, election_type: primary|general|special, label, certified)
- `source_files` (file_id = sha256, election_id, filename, sha256, stored_path, adapter, adapter_version, staging_id, ingested_at, row_count, status: active|superseded, superseded_by)
- `contests` (contest_id `<election>:<party|np>:<slug>`, election_id, file_id, source_ordinal, name_raw, name_display, contest_type: candidate|issue, party (primary ballot), jurisdiction, vote_for, vote_for_source: inferred|manual|unknown)
- `choices` (choice_id `<contest>:<slug>`, contest_id, source_ordinal, source_column, name_raw, name_display, party, choice_kind: candidate|yes|no|write_in|withdrawn|no_petition|over|under, file_id). Shares exclude over and under; every other kind counts.
- `precinct_results` (election_id, precinct_name, contest_id, choice_id, votes, file_id): rows only where the contest was on that precinct's ballot
- `precinct_sources` (election_id, precinct_name, precinct_name_raw, precinct_code_raw, source_row, file_id)
- `precinct_turnout` (election_id, precinct_name, party: ALL or code, registered, ballots_cast, ballots_blank, file_id)
- `out_of_county_results` (election_id, county_name, contest_id, choice_id, votes, file_id): footnotes and reconciliation only, never mapped
- `normalization_log`, `unmatched_precincts`, `ingest_events`, `geometry_repairs`: audit trail
- `boundary_sets` (boundary_set_id, geography: precinct|council_district|municipality|zcta|county, county, valid_from, valid_to exclusive, native_from (earlier lookups are retroactive), source, source_sha256)
- `features` (boundary_set_id, feature_id, name, jurisdiction, geom EPSG:4269); precinct feature_id = normalized precinct name
- `precinct_crosswalk` (precinct_set_id, target_set_id, precinct_name, feature_id, pop_share, area_share, split_share, method, weight_basis) and `crosswalk_log`; `census_blocks` (2020, pop)
- `geo_results` (materialized: election_id, contest_id, choice_id, geography, boundary_set_id, feature_id, votes, votes_exact, votes_allocated, precincts_exact, precincts_allocated, method: exact|allocated|mixed). Geography `precinct` is the identity mapping.
- `geo_contributions` (election_id, geography, feature_id, precinct_name, split_share, method, weight_basis): the per-precinct trace behind each area
- `geo_turnout` (election_id, geography, feature_id, party, registered, ballots_cast, ballots_blank), weighted like votes
- `geo_reconciliation` (per election, choice, geography: source = mapped + excluded + unassigned, ok)
- `feature_codes` (boundary_set_id, feature_id, code): BOE `PRECINCTID` per precinct, from `code_field` in the registry
- `address_files`, `voter_addresses` (zip5, house_no, street, precinct_code, precinct_codes, council_district, city_code): de-identified, one row per street address
- `census_releases`, `census_files` (table, filename, source_url, sha256), `census_stats` (release_id, geography, boundary_set_id, feature_id, metric, value, moe (90%), base, reliable), `census_log`
- `parcel_stats` (file_id, geography, boundary_set_id, feature_id, metric, value, n)
- `parcel_files`, `parcels` (pid, residential, apartment, units_estimate, units_method, owner_llc, owner_address_differs, likely_rental, grade, grade_score, building_value, property attributes, site address, `attributes` JSON of the other non-owner columns, x_ft/y_ft in EPSG:3735), `parcel_assignments` (precinct_name and precinct_method: point_in_polygon|nearest|voter_address|unassigned; council_district and council_method: point_in_polygon|voter_address|nearest|not_in_columbus|unassigned; geometry_precinct/geometry_council kept where the voter file overrode them; voter cross-check and agreement flags), `parcel_log`

Every displayed number traces back through `geo_results` to `precinct_results` to a `source_files` row.

## Data rules (non-negotiable)

1. **Never drop rows silently.** Every join, filter, or dedupe reports rows in, rows out, and why. Unmatched precincts go to a log table, not the floor.
2. **Every geography is tied to an election date.** Precinct keys are `(county, precinct_code, election_date)`. Boundary lookups pick the set whose validity window covers the election date. No "current boundaries" default.
3. **Prefer exact aggregation over allocation.** If a precinct nests in a target unit (by its jurisdiction attribute or by geometry within tolerance), aggregate exactly. Allocate only the precincts that actually split, weighting by 2020 census block population (TIGER `tabblock20` `POP20`; the same blocks will later carry district demographics). Fall back to area only for a precinct piece with zero block population, and log it. Record `method`, `split_share` and `weight_basis` for every output row. A precinct nests when one unit holds at least 99% of its block population (`NEST_TOLERANCE`); otherwise it is allocated, with pieces under 0.1% dropped and renormalized. Every residual, exclusion and fallback goes to `crosswalk_log`. Crosswalks live in `precinct_crosswalk` and are built by `precinctmap boundaries load`.
4. **Totals must reconcile.** After aggregation, totals across features equal source totals within rounding, minus explicitly logged exclusions (e.g. precincts outside Columbus for council districts). Assert it.
5. **Ingest is staged, never blind.** Uploads go to staging. The review report lists the detected election, contests and choices, the precinct match rate against the boundary set for that date, unmatched precincts, and a check against any county-total row in the file. Nothing commits until the admin approves. Re-ingesting the same sha256 is a no-op; a corrected file replaces its predecessor and logs it.
6. **Fail loudly on bad input.** Strip BOMs, normalize headers and precinct codes, and log every normalization. Unknown layouts raise a specific error; they never get a best guess.
7. **Don't invent formats.** Write adapters only from real samples in `data/samples/`. Results layouts differ by year, so each vintage gets its own adapter version. If there's no sample, stop and ask.

## Geography notes

- **Precinct:** native unit. Key on the normalized precinct *name* (pad single-digit wards: `BEXLEY 1-A` → `BEXLEY 01-A`), never `PRECINCT CODE`, which is a row ordinal that shifts between elections. Use the boundary set valid on the election date. The only precinct file is the July 2025 BOE file; no older vintage can be obtained, so elections before it use it retroactively and are labeled that way. For now every boundary set is valid for any election from 2000 on (decision 2026-10-22); replace with dated vintages if older files turn up. For those elections, HAMILTON-A is rebuilt as HAMILTON-A ∪ OBETZ-D (OBETZ-D was carved from it).
- **Municipality/township:** cities and villages plus unincorporated townships, so the county map has no holes. Aggregate exactly by precinct name prefix (validated against municipal contest participation). Villages with no precincts of their own (Brice, Lockbourne, Harrisburg, Lithopolis, the Franklin part of Pickerington) are allocated from their host township precinct by block population within the TIGER place of the matching vintage. This may change later. TIGER county subdivisions are not usable directly: Ohio cities sit inside township subdivisions. Columbus annexations change boundaries often, so vintage matters.
- **ZIP code:** Census ZCTA5 polygons (TIGER, ZCTA 2020 definitions), labeled "ZIP code area (ZCTA)" since ZCTAs approximate USPS ZIPs. Precincts rarely nest in ZCTAs, so most rows are allocated. ZCTAs that cross the county line show the Franklin County portion only and say so.
- **County:** TIGER county outlines, used for clipping, the "no data" mask, and context. Not a results geography yet.
- **Columbus council district:** only precincts inside Columbus count. Everything else renders greyed out with a "not in Columbus" tooltip. If an election predates the district map, allow it, but label it clearly as district boundaries applied retroactively. The district file (`Columbus_City_Council_Districts.geojson`) is the original and current map, first used in 2023 (`native_from`), with no end date; earlier elections use it retroactively (valid from 2000) and the API adds a note saying so. Membership comes from the precinct name prefix, not geometry, so non-Columbus slivers are ignored. Columbus precinct population outside every district polygon is renormalized across the districts the precinct touches, and logged.
- **County coverage:** scope starts with Franklin County. Parts of Columbus lie in Delaware and Fairfield counties. Until those counties' results are ingested, those areas must show as "no data," not zero, and Columbus-wide totals must say they're Franklin County only.
- **Results layouts:** `fcboe_sheets_2016` (2016 primary: one sheet per party ballot plus Questions & Issues, read with merged cells via `read_workbook`; rows are precinct splits, summed into precincts by BOE code; no over/under columns, so a contest is off the ballot when all its cells are 0; each choice records its `source_sheet`), `fcboe_classic_2020` (2020 primary: 4 header rows, 4 vote-type columns per choice, contests delimited by OVER/UNDER VOTES, party per choice), `fcboe_wide_2024`, `fcboe_wide_2025`. In the 2020 layout, contests sharing a name and party (central committees) get the area of the precincts that carried them, since the file names no district; its SENATE/HOUSE attribute columns look swapped, so they aren't used.
- **Registry:** every boundary set, its validity window and its derivation lives in `config/boundaries.toml` (reviewed in git). Display-name typo fixes live in `src/precinctmap/ingest/corrections.py`; add entries only for typos seen in a real file. Combined contests (an extra contest that sums contests split by district, e.g. the 2020 Democratic delegates-at-large per congressional district → "(all districts)") live in `src/precinctmap/ingest/combine.py`: reviewed entries per election, applied at staging, members kept, choices matched by name, precinct votes summed (split precincts carry each part's district contest), checks built from the members'; re-ingest with `--reprocess` after adding one.
- **Parcels:** located by the auditor's point (EPSG:3735), using the precinct and council sets valid on the file's `--as-of` date. A point outside every precinct goes to the nearest one within 500 ft. Council districts apply only to parcels in Columbus precincts: point-in-polygon, then the nearest district. **The voter file overrides geometry** (decision 2026-10-21): where it has the address, its precinct and district win unless point-in-polygon gave the same answer, the method becomes `voter_address`, the geometry answer is kept in `geometry_precinct`/`geometry_council`, and each override is logged. When an override crosses a jurisdiction, the municipality follows the new precinct (its majority municipality in the crosswalk). Geometry and voter file agree on 99.95% of precincts (136 overrides on the 2026-10-21 files). Address ranges ("400 - 404 OAK ST") match voter addresses on the same side of the street only.
- **Residential property layer:** the universe is auditor class R with a dwelling (`PCLASS='R'`, `DWELTYP='1'`) plus apartment buildings (class C, land use 401-403), which always count as likely rentals. Housing units: 1 per class R parcel, 2 or 3 for two- and three-family (land use 520/530); apartments are estimated per 2020 census block (block `HOUSING20` minus the block's other units, shared by building value), at least the distinct unit numbers with a voter, and clipped to the class range (401: 4-19, 402: 20-39, 403: 40+) — see `src/precinctmap/parcels/units.py`. Valuation and grade statistics cover class R homes only. Likely rental = 'LLC' in `NAME1-3`, or the owner address (`OWNER_ADD1/2`: house number or ZIP) differs from the site address. Do not use `MAILAD*` for this: it is the tax-bill address, often a mortgage tax-service PO box, and flags 30% of homestead parcels (`OWNER_ADD` flags about 6%). Only the resulting booleans are stored. Grade score: A=5 ... E=1, +/-0.2 per step; S/X codes are not scored. `COND` is blank in the 2026 file. Valuation statistics skip zero values. Per-area statistics (`parcel_stats`) come from each parcel's point in every geography (medians are never built from precinct parts), and per-geography totals are asserted. The metric catalog is `src/precinctmap/parcels/stats.py`.
- **Census demographics (ACS 5-year):** block-group estimates (tracts for B05002, which isn't published lower) are split across 2020 blocks by `POP20` (people) or `HOUSING20` (households), and each block counts in the area holding its interior point, for every geography (council: Columbus-precinct blocks only). Shares are summed numerators over summed denominators; median income is interpolated from B19001 brackets (top-coded at $200,000); MOEs follow Census derived-estimate formulas; CV > 30% is flagged unreliable and hatched. Labels are neutral demographic names, never political ones (decision 2026-10-21). Measure catalog and line numbers: `src/precinctmap/census/tables.py`; method and rationale: `project-docs/census.md`.
- **Data bundles** (`src/precinctmap/bundle/`): every loaded table except `geo_*` (rebuilt on load) as zstd Parquet (geometry as GeoParquet, EPSG:4269 coordinates labeled CRS84), the results spreadsheets and filtered ACS files, `manifest.json` (rows and sha256 per file, schema version) and `DATA.md` (vintage from the store; publisher, update location, cadence, terms from `bundle/sources.py`). Published as GitHub release assets (decision 2026-10-22), including the de-identified voter address table. Export only with the app stopped. When a dataset's source or update location changes, edit `bundle/sources.py`.
- **CRS:** store in EPSG:4269. Do area math in EPSG:3735 (Ohio South ftUS). Serve EPSG:4326 GeoJSON to the client. Repair geometry with `shapely.make_valid` and log fixes.

## App behavior

- **Selection flow:** year → election → contest → choice or metric → geography. Each control lists only options that have data. Selection lives in URL query params so a view can be shared by link.
- **Metrics:** for issues, yes share, yes−no margin, and total votes. For candidates, the selected candidate's share, the margin between the top two, and the leader by area. Turnout is its own catalog entry (`<election_id>:turnout`, first in the contest list, never the default) when the file has registered voters and ballots: turnout %, ballots cast, and per party ballot (its choices) the share of registered voters, the share of ballots cast, and the count (decision 2026-10-22: both party denominators). The files' registered-by-party counts are never a denominator: they count voters by their last primary ballot.
- **API shape:** geometry and results are separate. `GET /api/geo/{geography}?date=` returns cached, simplified GeoJSON keyed by `feature_id`. `GET /api/results?...` returns compact JSON keyed by `feature_id`. The client joins them through MapLibre feature-state, so changing the contest doesn't refetch geometry. Plus `GET /api/catalog` and admin `POST /api/ingest`. Implemented in `app/api/` over `src/precinctmap/serve/`:
  - `GET /api/catalog`: years, elections, contests with choices (kind, party), geographies that have results.
  - `GET /api/turnout?election=&geography=` (same shape as `/api/results`; `v` = ballots per party), `/api/turnout/detail`, `/api/turnout/export.csv`. The client routes `:turnout` contests there (`app/web/src/api.ts`).
  - `GET /api/geo/{precinct|council_district|municipality|zcta|county}?date=`: simplified GeoJSON (~3 m), ETag + gzip, properties `feature_id`, `name`, `jurisdiction`.
  - `GET /api/results?election=&contest=&geography=`: `features[feature_id] = {v: votes per choice in choices order | null if not on the ballot, reg, bal, method, pe, pa}`, plus `choices[].counts` (false for over/under), totals, and notes (retroactive, Franklin-only, not-in-Columbus exclusions, ZCTA caveat).
  - `GET /api/results/detail?...&feature=`: votes and shares, method, contributing precincts with split shares, turnout, source file and sha256.
  - `GET /api/export.csv` and `/api/export.geojson`, same parameters.
  - `GET /api/property?metric=&geography=`, `/api/property/detail?geography=&feature=`, `/api/property/export.csv?geography=`: residential property statistics (no PII). The client's **Data** selector switches between election results (default) and property (`?d=property&pm=<metric>&g=<geography>`).
  - `GET /api/census?metric=&geography=`, `/api/census/detail`, `/api/census/export.csv`: the same shape as property (one `MeasureStats` model), plus `moe` and `reliable` per feature and the metric's `universe`. Client: `?d=census&pm=<metric>&g=<geography>`; both datasets share `app/web/src/measures/`.
  - Admin: `POST /api/ingest` (multipart: file, election_date, election_type, certified, reprocess), `GET /api/ingest/{staging_id}`, `POST /api/ingest/{staging_id}/commit` (commits, then aggregates and reconciles).
- **One writer:** DuckDB allows one read-write process. While the API runs, CLI commands that open the store exit with a "store is open in another process" message; use the admin endpoints or stop the API.
- **Map legibility:** use colorblind-safe palettes, sequential for shares and diverging around 50% or zero margin. **Never use party red/blue**, because the tool is nonpartisan and ballot issues aren't parties. Use fixed bins by default and show them in the legend. Dim or hatch areas below a minimum vote count and show the count in the tooltip.
- **Implemented map rules (Phase 6):** areas with fewer than 25 valid votes get a diagonal hatch rising left to right ("/", `LOW_VOTE_THRESHOLD`), the only diagonal pattern. White means not on the ballot, no ballots cast, or no data. Gray means "within 5 points" only. "Not in Columbus" is gray with dots. Legend swatches are drawn from the map's own pattern tiles (`patternBackground`). Outside Franklin County is an opaque mask under the basemap labels. Palettes and their validation: `project-docs/palette.md`. MapLibre 6 needs `setWorkerUrl` (see `app/web/src/map/view.ts`).
- **Table:** a sortable table of the mapped statistic for the current geography (area, value, the votes or parcels behind it, notes), built from the same values the map colors (`app/web/src/ui/table*.ts`). A Map / Table / Map and table switch sits above the map; side by side is the default at 1180px and wider and isn't offered below that. Areas without a value sort last; clicking a name opens the detail panel. The view choice is a display preference, not part of the URL.
- **Detail panel:** clicking an area shows every choice's votes and share, the method (exact or allocated) with the split share, and the source file name.
- **Export:** CSV and GeoJSON of the current view.
- **Admin:** an upload page drives the same staging, review, and commit flow as the CLI, and shows the review report before the commit button is enabled. Built as `app/web/admin.html` (`src/admin/`), served by FastAPI at `/admin` behind the login.
- **Access:** the map is public, with no viewer login (decision 2026-10-21). Only `/admin` and `/api/ingest/*` need a login: HTTP Basic from `PRECINCTMAP_ADMIN_USER` / `PRECINCTMAP_ADMIN_PASSWORD`. It fails closed on missing or placeholder passwords, and unsafe methods require the `X-PRECINCTMAP-Admin: 1` header (CSRF guard). Replacing an election's loaded file requires an explicit `replace` confirmation. Docker publishes on `PRECINCTMAP_HOST` (default `127.0.0.1`) and `PRECINCTMAP_PORT` (default 8000; the container listens on the same port); put HTTPS in front before exposing it. No voterfile data in the app.

## Interface theme

Neutral, unbranded chrome: dark slate header (`--ink`) with an optional organization name from `VITE_ORG_NAME` (build time, blank by default) and a 2px `--rule` line below it; body text `--ink` on `--surface`; `--accent` for links and primary buttons; system font stack. Tokens live in `app/web/src/styles.css`. Sentence case everywhere. Interface colors are for the chrome, never the choropleth.

## Privacy

- **The voter file is used only as a de-identified address -> precinct/council-district table** (decision 2026-10-21). `src/precinctmap/parcels/voterfile.py` is the only reader. Its queries name only `HOUSE NO`, `RES STREET`, `RES ZIP`, `PRECINCT`, `CITY OR VILLAGE`, `CITY COUNCIL WARD/DISTRICT` and `RES APT`, and rows collapse to one record per street address (`RES APT` survives only as a count of distinct unit numbers).
- Names, voter IDs, birth dates, party, registration dates, vote history and per-address voter counts are never read, stored, logged or shown. Never log or print individual voter rows; surveys of the file report aggregates only.
- Data about individual addresses and parcels may be shown, as long as no PII is displayed. Auditor owner names and mailing addresses (`NAME1-3`, `OWNER_ADD1-2`, `MAILAD1-4`) are dropped at read and never stored.
- Test fixtures stay synthetic: the voter fixture's fake name and ID columns exist only to prove they never reach the store.
- Results data is public, but keep `data/` gitignored anyway.

## Testing

- Golden tests (`tests/golden/`) reproduce the BOE's certified county totals for selected contests, extracted by `scripts/extract_official_totals.py` (openpyxl, no precinctmap code), through the store and every geography. There is no prior analysis to reproduce. They skip when no local store exists. If a change moves a golden number, stop and explain why before updating it.
- Each ingest adapter gets a fixture test plus a malformed-input test.
- API tests run against a small seeded DuckDB. Web tests cover the selection state and the URL round-trip.
- Mark BigQuery tests `@pytest.mark.bq`.

## Working style

- Plan before large changes: list the files you'll touch and the open questions, then proceed.
- Small, typed functions. Public functions document units, CRS, and their election-date assumption.
- Use DuckDB for heavy tabular work and GeoPandas for geometry.
- When a source format changes, add a new adapter version instead of branching inside an old one.
- End each phase with a short note: what changed, what you found in the data, and decisions you need from me.
