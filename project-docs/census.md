# Census demographics (ACS)

The map's **Census demographics** dataset shows American Community Survey (ACS) 5-year estimates for every geography the app maps: precinct, Columbus council district, city/village/township and ZIP code area. The current release is ACS 2020–2024, published January 2026. The next one, 2021–2025, is due around December 2026.

## Why these measures

The measures were picked because research on recent U.S. elections ties them most consistently to area-level differences in Democratic and progressive vote share. The app labels them neutrally ("Bachelor's degree or higher", not "progressive indicator") and never presents them as political. They describe places, not how any individual votes. Reading individual behavior off area data is the ecological fallacy.

| Group | Measures | Why |
|---|---|---|
| Education | Bachelor's or higher; graduate degree | College education has become one of the strongest dividing lines in U.S. voting since 2016 ("education polarization"), for White voters especially. |
| Age and household | Adults 18–34; never married | Younger and unmarried voters lean more Democratic than older and married voters (the "marriage gap"). |
| Race and ethnicity | White, Black, Hispanic/Latino and Asian shares | Large, long-standing differences by race and ethnicity. Hispanic and Asian voters shifted measurably toward Republicans between 2016 and 2024, so these relationships are changing. |
| Immigration | Born outside the U.S.; not a U.S. citizen | These mark immigrant communities. Non-citizens can't vote, so this describes residents, not the electorate. **The ACS doesn't ask about legal or immigration status**, and nothing here estimates it. |
| Housing and income | Renter households; rent-burdened renters; median household income; below 200% of poverty | Renters lean more Democratic than homeowners. Income's link to vote choice has weakened and partly reversed as education polarization grew: high-income, highly educated areas and low-income areas can both lean Democratic. Show both ends rather than one "income" score. |
| Urbanism | Transit, walking or bike commuting; work from home; people per square mile | Density and the urban–rural divide are among the strongest geographic predictors. Working from home tracks professional, highly educated work. |

The ACS doesn't cover several strong predictors: religion and religious attendance, union membership, gun ownership and party registration.

## Method

1. **Fetch.** `precinctmap census fetch --year 2024 --as-of D` streams each national table from the Census Bureau's table-based summary file (no API key) and keeps only the county's block groups, tracts and county row. The files go to `data/raw/census/acs5-2024/`, and each file's sha256 is recorded at commit.
2. **Source unit.** Every table uses block groups (952 in Franklin County), except place of birth and citizenship (B05002). Census publishes that table only for tracts (328), so the immigration measures are smoother at precinct level.
3. **Allocate.** A block group's (or tract's) estimates are split across its 2020 census blocks. People-based tables are split by block population (`POP20`) and household tables (B25003, B25070, B19001) by housing units (`HOUSING20`). A unit with no population or housing falls back to land area, and that fallback is logged.
4. **Assign.** Each block counts in the area holding its interior point, using the boundary sets valid on `--as-of`. A point outside every polygon goes to the nearest area within 500 ft. Council districts take only blocks in Columbus precincts, as parcels do, and each gets its nearest district if it's in none.
5. **Combine.** Counts are summed. Shares are summed numerators over summed denominators, never averages of percentages. Median household income is interpolated linearly within the summed income brackets (B19001). It's top-coded at $200,000, shown as "$200,000 or more". Density is ACS population over 2020 block land area (`ALAND20`).
6. **Margins of error (90%).** These follow Census guidance for derived estimates:
   - **Sums:** use the root of the summed squared margins. Within a unit, a zero estimate's margin counts only once.
   - **Proportions:** use the proportion formula, switching to the ratio formula when the radicand is negative.
   - **Allocated parts:** a unit's share scales both its estimate and its margin. This is an approximation.
   - **Median income:** the margin uses the standard error of the cumulative share at the median bracket, calculated from bracket margins, in place of a published design factor.
7. **Reliability.** An estimate is flagged, and hatched on the map, when its coefficient of variation (MOE ÷ 1.645 ÷ estimate) is above 30%, or when it's zero with a nonzero margin. Small shares in single precincts are often unreliable. Noncitizen share, for example, is reliable in only about 19% of precincts.
8. **Checks.** The review compares each table's block-group or tract sum with the published county row (all equal for 2020–2024). It also asserts that mapped counts equal the source units' estimates times the share placed. `precinctmap census load ... --commit` writes only after the review. Recommitting the same files does nothing, and changed files replace the release and are logged.

## Updating to a new release

```bash
docker compose stop
uv run precinctmap census fetch --year 2025 --as-of YYYY-MM-DD
uv run precinctmap census load  --year 2025 --as-of YYYY-MM-DD            # review
uv run precinctmap census load  --year 2025 --as-of YYYY-MM-DD --commit
docker compose up -d
```

The map shows the release with the latest end year. Check the table shells for line changes before loading a new vintage. The line numbers live in `src/precinctmap/census/tables.py`.
