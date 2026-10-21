# Phase 0 survey (2026-10-20)

Inspection used throwaway scripts outside the repo. No project code written.

## Results files

All three files are the Franklin County BOE wide export. One sheet each, `.xlsx` (UTF-8 XML), no BOM, no merged or hidden structure.

| File | Election | Precinct rows | Pseudo-rows | Columns | Contests |
|---|---|---|---|---|---|
| `2025-Primary-Election-Official-Precinct-Results.xlsx` | 2025-05-06 primary | 888 | 3 | 101 | 19 |
| `2025-General-Election_EXPORT_Official.xlsx` | 2025-11-04 general | 889 | 8 | 622 | 128 |
| `2026-Primary-Election_EXPORT_Official.xlsx` | 2026-05-05 primary | 889 | 8 | 768 | 231 |

### Shared layout

- **Row 1:** contest name, repeated across that contest's columns. Each contest is one contiguous run, and no contest name repeats.
- **Row 2:** party code (`Dem`, `Rep`, `Lib` or `Non`). Blank for ID columns.
- **Row 3:** choice label, or `VOTERS` / `BALLOTS CAST` for the turnout columns.
- **Rows 4 and on:** `COUNTY NUMBER` (always 25), `PRECINCT CODE` (text `0001`…), `PRECINCT NAME`, turnout columns, then contest columns. All values are numeric, with no blanks and no fractions.
- **Last row:** `ZZZ` / `COUNTY TOTALS`. In every column of every file, the sum of the rows above it equals the `ZZZ` row exactly.
- **Every contest ends with `OVER VOTES` and `UNDER VOTES`.** Other non-candidate labels: `Write-in`, `Candidate Withdrawn`, `No Valid Petition Filed`, `No Other Valid Petition Filed`.
- **No vote-for count anywhere.** It can be inferred from `cands + under + k·over = k·ballots` in about 75% of contests. The rest are ambiguous because only some ballots in a precinct carry the contest (split ballot styles).

### Differences between primary and general

| | 2025 primary | 2026 primary | 2025 general |
|---|---|---|---|
| Party | contest prefix (`Dem For …`) and row 2 | same | in the choice label (`Rep Les Carrier`); row 2 is `Non` |
| Turnout columns | registered and ballots, total plus Dem/Non | total plus Dem/Rep/Lib/Non | registered and ballots total, plus blank ballots |
| Name quirks | `For Member of Council - City of X`; `State Issue 2 -` (trailing dash) | `… Governor -` | `Infrustructure` (source typo, kept raw) |

### Encoding defects

- 2025 general, column 1422: `GeraldÂ\xa0Dixon`. This is a UTF-8 non-breaking space mis-decoded as cp1252. Repair it and log the repair.
- No other non-ASCII characters and no stray whitespace.

### Precinct key

- **`PRECINCT CODE` is a row ordinal, not an ID.** OBETZ-D was added after the May 2025 primary, so codes 0751–0888 shifted by one: 138 codes point to different precincts in May 2025 than in November 2025. Codes are stable between the 2025 general and the 2026 primary.
- **`PRECINCT NAME` is the stable key.** Results drop the ward padding outside Columbus (`BEXLEY 1-A`); the shapefile keeps it (`BEXLEY 01-A`). Padding single-digit wards makes all three elections match the shapefile 100%: 888/888, 889/889 and 889/889. The 2025 primary lacks OBETZ-D.
- **Pseudo-rows** are named `<X> County`, with registered = ballots = 0. They take the codes after the last real precinct, so their codes also vary by election. They carry votes from other counties in multi-county contests. Examples:
  - 2025 general, Delaware: 91,694 votes, including the Columbus bonds and Westerville issues.
  - 2026 primary, Pickaway: 28,877 votes, including the 15th Congressional District.

  The `ZZZ` totals include these rows.

### Proposed adapters

Two layout groups, so two adapters. See the 2024 section below for `fcboe_wide_2024`.

`fcboe_wide_2025` covers the 2025 primary, the 2025 general and the 2026 primary.

- **Detection:** row 1 starts `COUNTY NUMBER, PRECINCT CODE, PRECINCT NAME`; row 3 has `VOTERS` / `BALLOTS CAST`; the file has a `ZZZ` row.
- **Primary vs general:** handled from the header rows, not by branching on file name.
- **Turnout columns:** parsed from their headers, so a varying set of parties is handled.
- **Fixtures:** one primary and one general.

## 2024 files (second layout group)

| File | Election | Precinct rows | Pseudo-rows | Columns | Contests |
|---|---|---|---|---|---|
| `2024-Election-Results-CSV.xlsx` | 2024-03-19 primary | 888 | 6 | 118 | 65 |
| `Official-Results-by-Precinct.xlsx` | 2024-11-05 general | 888 | 16 | 75 | 43 |

I identified the elections by their contests: Biden/Phillips in the first, Harris/Trump in the second. The file names don't say, and both sheets are named `25ElectionResultsCSV`. The election date and type will be set at review time, not guessed from the file name.

### Differences from the 2025 layout

- **Precinct codes are letters** (`AAN`, `AAO`…), and pseudo-rows have a blank code.
- **Turnout columns** are `REGISTERED VOTERS` and `TOTAL VOTERS`. The primary adds per-party ballot columns (`Democratic`, `Republican`, with row 3 blank). There's no blank-ballots column.
- **No `OVER VOTES` / `UNDER VOTES` columns.**
- **A blank cell means the contest wasn't on that precinct's ballot.** It's not a zero. In the 2024 general, the 3rd and 15th Congressional Districts partition the precincts 543 / 350; five split precincts appear in both. Blanks become absent rows, never zeros.
- **Pseudo-rows:**
  - In the primary they're named `X County` and carry no votes.
  - In the general they carry bare names (`Clark`, `Delaware`…) and votes in 7 columns, such as the 15th Congressional District. Those 7 columns are where the precinct sum differs from `ZZZ`.
- **Text defects in the primary:**
  - 13 names with mojibake non-breaking spaces (`LaurelÂ\xa0BeattyÂ\xa0Blunt`)
  - commas replaced by double spaces (`State Central Committee  Man`, `Frank J. Reed  Jr.`)
  - source typos (`(2nd Distict)`, `(9th District` with no closing parenthesis, `10Th`)

  `name_raw` keeps each name as it came; `name_display` is normalized, and every repair is logged.

### Precinct boundaries for 2024

Names match the July 2025 shapefile 888/888, missing only OBETZ-D. Registered-voter drift between consecutive elections has a median of 1–3%. The only change that looks like a redraw is HAMILTON-A, which went from 1,004 to 513 registered voters between May and November 2025, when OBETZ-D was carved from it.

Wards 16 and 39–41 also lost 10–20% of their registered voters in mid-2025, spread evenly across their precincts. That looks like voter-roll maintenance, not a boundary change, but this is an inference.

**Decision:** the July 2025 file applies retroactively to the 2024 primary, the 2024 general and the 2025 primary, labeled as retroactive. For those elections, HAMILTON-A is rebuilt as HAMILTON-A ∪ OBETZ-D.

## Decisions (2026-10-20)

1. **No older precinct file exists.** The 2025 file is used retroactively, as above.
2. **Allocation weight:** 2020 block population (TIGER `tl_2020_39_tabblock20`, `POP20` field). I'll download it in Phase 3. It also enables district demographics later.
3. **Council districts:** the GeoJSON is the only map ever used. Valid from 2023, open-ended.
4. **Villages without precincts** are allocated by geometry for now.
5. **Vote-for:** a display attribute, nullable. Shares don't need it, and the 2024 files have no over/under votes to infer it from.
6. **Write-in, Candidate Withdrawn and No Valid Petition Filed** count as choices in share denominators. Over and under votes don't.
7. **Out-of-county votes:** stored and reconciled, and used in footnotes only. Never mapped.

## Boundary files

| File | CRS | Features | Vintage | IDs | Notes |
|---|---|---|---|---|---|
| `franklin_precincts_2026/VotingPrecinct.shp` | EPSG:3735 | 889 | created 2025-07-30, last edited 2025-09-18 | `NAME` (unique), `PRECINCTID` (`01001A`), `WARDCODE`, `GlobalID` | 7 invalid geometries, fixed by `make_valid` (85 become MultiPolygon). UTF-8 `.cpg`. Same files as `extracted/` and the 7 `Voting_Precinct_*.zip`. |
| `Columbus_City_Council_Districts.geojson` | EPSG:4326 | 9 | `LAST_EDIT_DATE` 2024-11-26 | `DISTRICT` 1–9 | 3 invalid geometries. Carries 2020 population attributes, not needed. |
| `tl_2026_39_place.zip` | EPSG:4269 | 38 near Franklin | TIGER 2026 | `GEOID`, `NAME` | |
| `tl_2026_us_zcta520.zip` | EPSG:4269 | 57 touch Franklin | ZCTA 2020 definitions in TIGER 2026 | `ZCTA5CE20` | 826 MB unzipped. Read with a bbox filter and clip at load. |
| `tiger_dl/tl_2026_us_county.zip` (downloaded) | EPSG:4269 | — | TIGER 2026 | `GEOID` 39049 | |
| `tiger_dl/tl_2026_39_cousub.zip` (downloaded) | EPSG:4269 | 24 in Franklin | TIGER 2026 | `NAMELSAD` | |

### Jurisdiction field

The precinct file has no explicit jurisdiction field. Two sources stand in for one:

- **Name prefix** (`COLUMBUS`, `BLENDON`, `UPPER ARLINGTON`…), giving 46 jurisdictions.
- **`PRECINCTID[:2]`**, which is the township code. It isn't the municipality: code 21 covers both DUBLIN and WASHINGTON.

The name prefix is validated by contest participation in the 2025 general. All 549 COLUMBUS-named precincts voted in City of Columbus contests, and no other precinct did.

### Nesting

Area overlap of precincts in EPSG:3735:

| Target | Precincts split ≥1% | ≥10% | ≥25% |
|---|---|---|---|
| Council districts (Columbus precincts only) | 117 of 549 | — | — |
| Council districts (all precincts touching) | 284 | 200 | 167 |
| TIGER places | 198 | 79 | 64 |
| TIGER county subdivisions | 152 | 21 | 5 |
| ZCTAs | 272 | 161 | 96 |

- **Council districts.** Many Columbus precincts are genuine splits, around 50/50: 23-B, 58-I, 26-C and others. That's plausible, because council seats are elected citywide, so the BOE has no reason to follow district lines. The 167 non-Columbus precincts that touch a district do so by slivers of 1–10%, which is line misalignment. The jurisdiction rule excludes them. 81 Columbus precincts have 1–15% of their area outside every district polygon, a mismatch between the city and BOE files (both are current), not annexation. Handled by renormalizing and logging.
- **Municipality/township.** Precincts nest exactly by name prefix. TIGER county subdivisions don't fit because Ohio cities sit inside township subdivisions: Dublin is inside Washington township. Five places have no precincts of their own; their voters sit inside a township precinct:
  - Brice: TRURO-B
  - Lockbourne: HAMILTON-B
  - Harrisburg: PLEASANT-C
  - Lithopolis: MADISON-A
  - Pickerington: MADISON-E
- **ZCTA.** Allocation will be the norm, not the exception.
- **County outline.** 7 precincts have 1–2% of their area outside the TIGER county outline. That's line misalignment, so ignore it below a tolerance.

## Schema revisions proposed

- **Precinct key:** `(county, precinct_name_norm, election_date)`. Keep `precinct_code_raw` per election for traceability, never as a join key.
- **`contests`:**
  - add `party` (the primary ballot) and `source_ordinal`
  - add `vote_for` and `vote_for_source`, one of `inferred`, `manual` or `unknown`
- **`choices`:** add `choice_kind`, one of `candidate`, `yes`, `no`, `write_in`, `withdrawn`, `no_petition`, `over`, `under`. Over and under votes are stored but excluded from share denominators.
- **`precinct_turnout`:** add `party`, using `ALL` for the totals; add `ballots_blank` (nullable).
- **New `out_of_county_results`** (election_id, contest_id, choice_id, county_name, votes): pseudo-rows go here. Reconciliation becomes `ZZZ` = Σ precincts + Σ out-of-county.
- **New `precinct_crosswalk`** (precinct boundary_set, target boundary_set, precinct_key, feature_id, share, method, weight_basis): built once per pair of boundary sets, then reused by every election.
- **New log tables:** `normalization_log` and `unmatched_precincts`.
- **`geo_results`:** add `weight_basis`.
