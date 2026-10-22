# Project notes

Status as of 2026-10-21, at the end of Phase 7.

## What was built

- **`precinctmap` library** (`src/precinctmap/`):
  - **Staged ingest** of Franklin County BOE precinct exports, with six adapters (`fcboe_sheets_2016`, `fcboe_general_2016`, `fcboe_classic_2020`, `fcboe_general_2020`, `fcboe_wide_2024`, `fcboe_wide_2025`) and exactly one allowed to claim a file. The 2020 layout splits same-name Democratic and Republican contests by party, and names repeated central-committee contests by the precincts that carried them (the file gives no district).
  - **Logged normalization**, and a reviewed table of typo fixes for display names.
  - **Election identification from evidence:** file name, content and calendar. A file is blocked rather than guessed at.
  - **Review reports** with the precinct match rate, county-total reconciliation and a long-format re-total.
  - **Atomic commits:** re-ingesting the same file does nothing; replacing a loaded file needs confirmation; re-processing is supported.
- **Boundary registry** (`config/boundaries.toml`): every set has a validity window and the date it actually took effect.
  - Precincts: the July 2025 file, plus a retroactive copy with HAMILTON-A and OBETZ-D merged.
  - Municipalities and townships: built from precinct name prefixes, with five precinct-less villages cut out of their host townships.
  - Council districts, ZCTAs clipped to the county, and the county outline.
  - 2020 census blocks for weights.
- **Crosswalks** from precincts to target areas, weighted by block population. A precinct nests in an area when at least 99% of its population falls there. Council districts take only Columbus precincts. Every exclusion and residual is logged.
- **Results by geography** (`geo_results`, `geo_contributions`, `geo_turnout`). Reconciliation (source = mapped + excluded + unassigned) is asserted for every election, choice and geography. Golden tests reproduce 11 BOE certified county totals.
- **API** (FastAPI): catalog, simplified cached GeoJSON, compact results, area detail, CSV/GeoJSON export, and admin ingest behind HTTP Basic, which fails closed and requires a CSRF header.
- **Map client** (Vite, TypeScript, MapLibre): selection flow kept in the URL, choropleth via feature-state, fixed bins, validated palettes that never use party red or blue, distinct non-data states, tooltips, detail panel, export.
- **Admin page:** upload, review, then commit. Commit is enabled only for a ready report, and replacing a loaded file needs a confirmation.
- **Docker:** one container on one port (`127.0.0.1:8000`). The client is built into the image and DuckDB spatial is preinstalled.

**Verification:** all checks pass (Python: ruff, mypy strict, pytest; web: tsc, eslint, vitest, build). All five sample elections are cataloged with a 100% precinct match. Every column reconciles with the BOE county-total rows. A fresh `docker compose up --build` serves the map, the API and the admin page.

## Decisions on record

- **The precinct key is the normalized name,** with single-digit wards padded. `PRECINCT CODE` is a row number that shifts between elections.
- **Elections before 2025-07-30 use the July 2025 precincts retroactively.** No older file exists, and these elections are labeled as retroactive.
- **Allocation is weighted by 2020 block population.** Area is the fallback when a piece has no population, and every fallback is logged.
- **Council districts:** one map, valid from 2023. Population outside every district is renormalized; it's a mismatch between the city and BOE files.
- **Shares** exclude over and under votes. Write-ins, "Candidate Withdrawn" and "No Valid Petition Filed" count.
- **Other counties' votes** in joint contests are stored and reconciled, but used only in notes. They are never mapped.
- **Golden reference:** the BOE certified county-total rows. There is no prior analysis to reproduce.
- **Access:** the map is public; only admin needs a login.

## Residential property layer (2026-10-21)

- **Data:** auditor `Parcel.csv` (484,605 parcels) and the county voter file (`VOTERFILE.TXT`, as a de-identified address table only), both dated 2026-10-21.
- **Location:** every parcel is placed in a precinct, a municipality/township and a ZIP area by its point. All Columbus parcels also get a council district. Where the voter file has the address it overrides the geometry: 136 precinct and 54 council-district changes, each logged with the geometry answer kept.
- **Mappable measures:**
  - likely rentals (count and share), LLC-owned, owner elsewhere
  - median, mean and mean − median of building value and of total value
  - mean grade score, share graded D or lower, share graded B or higher
- **Countywide:** 416,826 residential parcels including 6,651 apartment buildings; 139,206 likely rentals, 84,630 LLC-owned. Estimated housing units 580,415 (2020 census: 580,903), 300,030 of them likely rentals (51.7%). Apartment unit methods: census block 3,641 buildings, class bound 2,753, voter units 257. Only 6.1% of homestead (owner-occupied) parcels are flagged, as a sanity check.
- **Not mappable:** building condition (`COND` is blank in the file). The tax-bill mailing address is not used for rentals; see `CLAUDE.md`.

## Deferred or known limitations

- **Vote-for** is unknown for every 2024 contest (no over/under columns) and for 26 contests in 2025–2026 with split ballot styles. It's used for display only.
- **Village allocation** (Brice, Lockbourne, Harrisburg, Lithopolis, Pickerington) uses 2020 population. The one direct check: Lockbourne cast 34% of HAMILTON-B's ballots in May 2025, against a 24.8% population share. Revisit if village results matter.
- **The 2024 primary export's out-of-county rows are empty,** even for multi-county contests. It isn't known whether that export omitted them or another county certified those contests.
- **Turnout is total-ballot turnout.** Turnout by party ballot in primaries is stored (`geo_turnout.party`) but not mapped.
- **Single-writer DuckDB:** command-line ingest needs the app stopped. The admin page avoids this.
- **Simplification:** GeoJSON is simplified per feature (~3 m). Shared edges don't show visible gaps at county zoom, but topology isn't preserved.
- **No dark mode** on the map page. The basemap and palettes are validated for light mode only.
- **The leader palette has three colors plus "another candidate".** Choropleths can't safely tell more colors apart.

## Next steps (likely)


1. **Delaware and Fairfield county adapters,** for full Columbus coverage. This needs samples, those counties' precinct boundaries, and a decision on how to show combined totals.
2. **More geographies:** Columbus wards (from `WARDCODE` and the precinct name), Ohio House and Senate districts, and school districts. Each is a registry entry plus a crosswalk; the API and client need no changes.
3. **BigQuery sync** of the catalog and `geo_results` to the project in `GOOGLE_CLOUD_PROJECT` (one way, after each commit). It's never queried at request time.
4. **Admin conveniences:** a history of uploads and commits from `ingest_events`, and boundary reloads from the admin page.
5. **District demographics** from the same 2020 blocks already used as weights.
6. **The November 2026 general:** its date is already in `catalog/calendar.py`. If the BOE changes the export layout, write a new adapter from the real file.
