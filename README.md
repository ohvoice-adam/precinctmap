# precinctmap: election results map

A map of Franklin County precinct election results. You can view results by precinct, ward, Columbus council district, city, village or township, and ZIP code area. Every number on the map traces back to an official Board of Elections results file.

- **Map:** `http://<server>:8000/` (or the port set in `PRECINCTMAP_PORT`). Anyone with the link can use it; there is no login.
- **Add an election:** `http://<server>:8000/admin`. This needs the admin login.

## Using the map

1. **Pick what to see** in the panel on the left, from top to bottom:
   - **Year** and **Election**.
   - **Contest.** Type in the filter box to narrow a long list. In primaries, contests are grouped by party ballot.
   - **Show.** For issues: yes share, the yes−no margin, or total votes. For candidates: one candidate's share, the margin between the top two, who leads in each area, or total votes.
   - **Turnout** is the first entry in each election's contest list when the results file has registered voters and ballots. It shows turnout (ballots ÷ registered voters) and ballots cast. In primaries it also shows each party's ballots three ways: as a share of registered voters (the party shares add up to turnout), as a share of all ballots cast, and as a count. Pick the party under **Party ballot**.
   - **Map by.** Precinct, Columbus council district, city/village/township, ward, or ZIP code area. A ward is all the precincts that share a prefix: COLUMBUS 01-A and COLUMBUS 01-B make up Columbus Ward 01. Places whose precincts have no ward number (BLENDON-A) are one area each.
2. **Read the colors with the legend.** Bins are fixed, so the same color always means the same range.
   - **Teal** (light to dark) means more of something: share, turnout or votes.
   - **Orange and purple** are the two sides of a margin. The legend names which side is which. **Gray** means "within 5 points".
   - Colors never stand for a party.
   - **White** means the contest was not on the ballot there, or nobody voted there. It is never "zero".
   - **Hatched (diagonal lines)** means fewer than 25 votes, so treat the percentage with care.
   - **Gray with dots** (council districts only) means the area is not in Columbus.
   - **Pale area outside the county line** means no data: only Franklin County results are loaded.
3. **Hover** over an area for its name, the value, and the number of votes.
4. **Click** an area for the full breakdown: every choice's votes and share, turnout, and the precincts it was built from. The panel also names the official file the numbers come from.
5. **See it as a table** with the **Map / Table / Map and table** switch above the map. On a wide screen the table sits beside the map by default. It lists every area with the mapped value, the number of votes (or parcels) behind it, and notes such as "fewer than 25 votes". Click a column heading to sort, and again to reverse. Areas with no value always sort last. Click an area's name to open its breakdown.
6. **Share a view** by copying the page address. It records everything you picked.
7. **Export** from the bottom of the left panel. **CSV (this measure only)** holds just what is on the map: one row per area with the mapped value, as a number and as displayed, the votes or parcels behind it, notes and the source file. The other links export everything for the view: every choice's votes (CSV or GeoJSON, for mapping software), or every property or census measure for the geography.

### Residential property

Switch **Data** to *Residential property*. You can map these measures by precinct, council district, city or township, ward, and ZIP area:
- the number and share of likely rentals, with LLC ownership and out-of-area owners shown separately;
- median and mean building value and total value, each also as **mean minus median**;
- the auditor's construction grade.

What the property measures mean:
- **Residential** means the auditor's residential class with a dwelling, plus apartment buildings (4 or more units), which the auditor classes as commercial. Apartment buildings always count as likely rentals.
- **Housing units** for apartment buildings are estimates: the auditor file has no unit counts, so each census block's 2020 housing units are shared among its apartment buildings by building value. Values and construction grade cover houses and condos only.
- **Likely rental** means the owner's name contains "LLC", or the owner's address is somewhere else. It's an estimate, not a registry: a second home or an owner who moved also counts.
- **Mean minus median** is positive where a few expensive properties pull the average above the typical home.
- **Building condition** is blank in the auditor's file, so it isn't mapped.
- Areas with fewer than 25 homes are hatched. No owner names or addresses are stored or shown.

### Census demographics

Switch **Data** to *Census demographics* for American Community Survey 2020–2024 estimates, by precinct, council district, city or township, ward, and ZIP area:
- **Education:** bachelor's degree or higher, graduate degree.
- **Age and household:** adults 18 to 34, never married.
- **Race and ethnicity:** White, Black, Hispanic or Latino, and Asian shares.
- **Immigration:** born outside the U.S., not a U.S. citizen, naturalized U.S. citizens (count), and naturalized citizens as a share of adult citizens (citizens 18 and older). The census doesn't ask about legal or immigration status.
- **Housing and income:** renter households, renters paying 30% or more of income on rent, median household income, below 200% of the poverty line.
- **Urbanism:** commuting by transit, walking or bike; working from home; people per square mile.

What to know:
- These are **survey estimates** with margins of error. The tooltip, table and detail panel show each value as "45.2% ± 6.1 points" (90% margin).
- **Hatched areas** have a large margin of error. Single precincts often do, especially for small groups. Council districts and cities are much more reliable.
- Census reports these numbers for block groups (and, for immigration, only for larger tracts). They're split across 2020 census blocks by population and added up for each area, so small-area values are approximate.
- Median income tops out at "$200,000 or more", the census's highest income bracket.
- Areas are described, not voters: no individual data is involved.

How the measures were chosen and calculated: `project-docs/census.md`.

### Things to know when reading the map

- **Estimated areas.** Precincts don't always fit inside council districts, ZIP code areas, or villages that have no precincts of their own. When a precinct is split, its votes are divided by where people live, using 2020 census population. Tooltips say "includes estimates from split precincts", and the click panel shows the share taken from each precinct. Precinct, ward and most city and township views need no estimates.
- **Franklin County only.** Parts of Columbus, Westerville, Dublin and other places lie in neighboring counties. Those votes are not mapped. The notes panel lists them when a contest has them.
- **Council districts.** Only precincts inside Columbus belong to a district. The notes panel says how many votes in the contest came from outside Columbus.
- **Older elections.** The only precinct map available is from July 2025. Elections before then use it as well, and the notes panel says so.
- **ZIP code areas** are the Census Bureau's ZIP Code Tabulation Areas, which approximate postal ZIP codes.

## Adding an election (admin)

1. Download the Board of Elections **precinct results export** for the election (an `.xlsx` file). Use it as it comes; do not re-save or edit it.
2. Go to `/admin` and log in.
3. Choose the file and select **Review file**. Nothing changes on the map yet.
4. Read the report:
   - **Ready to add to the map:** continue to step 5.
   - **Blocked:** the report lists the problems. The most common one is a file name with no year; enter the **Election date** and review again. Any other blocker means the file doesn't match what the tool expects. Don't work around it; ask the data team.
   - **Already loaded:** this exact file is already on the map.
   - Check **Precinct match** (it should be close to 100%) and **County-total check** (every column should reconcile). Also read the warnings.
5. Select **Add to the map**. If the election already has a file loaded, the page asks you to confirm that the new file should replace it, for example a corrected or certified version.
6. Follow **View it on the map** to check the result.

## For the administrator

### Running it

```bash
cp .env.example .env          # then set PRECINCTMAP_ADMIN_PASSWORD to a long random value
docker compose up --build -d  # map and admin on http://127.0.0.1:8000
```

- **Port and address.** `PRECINCTMAP_PORT` (default 8000) sets the port the app listens on. `PRECINCTMAP_HOST` (default `127.0.0.1`, this machine only) sets the address it's published on. Change either in `.env`, then run `docker compose up -d`.

- **Organization name.** Set `VITE_ORG_NAME` in `.env` to show your organization's name in the map header. It's applied when the web client is built, so rebuild after changing it. Leave it blank for no name.

- **Data folder.** Everything lives in `./data`, which is never committed:
  - `precinctmap.duckdb`: the database
  - `raw/`: every committed results file
  - `staging/`: review batches
  - `boundaries/`: the boundary files
  - `uploads/`: files uploaded through the admin page

  Back up `data/` with the app stopped.
- **Public access.** By default the app is reachable only from this machine (`127.0.0.1`). To publish the map, put a reverse proxy with **HTTPS** in front of it. The admin login uses HTTP Basic, which is only safe over HTTPS.
- **Admin password.** If `PRECINCTMAP_ADMIN_PASSWORD` is unset, shorter than 12 characters, or a placeholder, admin stays locked.
- **One process at a time.** The database allows one writer. While the app is running, command-line tools that open it stop with a "store is open in another process" message. Use the admin page instead, or stop the app (`docker compose stop`) first.

### First-time setup on a new machine

The `data/` folder comes with the clone and must stay writable by the user the container runs as: 1000 by default. If `id -u` and `id -g` print something else, set `PRECINCTMAP_UID` and `PRECINCTMAP_GID` in `.env`. Until boundaries and elections are loaded, the map says no elections have been loaded yet.

If the map says **"The map's data store isn't available"**, the message names the folder and the fix. Usually `data/` is owned by another user, for example root, after Docker created a missing folder. Run `sudo chown -R "$(id -u):$(id -g)" data`, then `docker compose up -d`.

**The quick way: load a data release.** Each data release on GitHub has `precinctmap-data.tar.gz`: every loaded election, boundary, parcel and census table, normalized, plus the original election spreadsheets and `DATA.md`. `DATA.md` lists each dataset's vintage, publisher, where to get updates, and how often it changes.

One script installs a release on a new machine or updates a running one:

```bash
scripts/update-data.sh              # latest release; shows what's in it, then asks before stopping the map
scripts/update-data.sh --dry-run    # download, verify and describe only; changes nothing
scripts/update-data.sh --tag data-2026-10-22.2   # a specific release
scripts/update-data.sh --file path/to/precinctmap-data.tar.gz --yes   # an archive you already have, no prompt
```

The script:
- **Downloads** the release, with `gh` if it's installed (needed while the repository is private), otherwise `curl`.
- **Verifies** the archive's checksum.
- **Builds** the app for the code you have checked out.
- **Shows** what the release contains.
- **Backs up** the current data to `data/backups/`.
- **Loads** the release and restarts the map.

The load checks every file's checksum, rebuilds the results by geography and re-checks every total. If anything fails, the script puts the previous data back and restarts the map on it. The map is down for about a minute.

When it finishes, the script prints the command to go back to the previous data. Backups are never deleted automatically, and each one is about 1 GB.

Loading a release replaces everything. If you uploaded elections through this server's admin page and they aren't in the release, they're replaced too. `precinctmap bundle info <file>` shows what a release contains without loading it.

**Or build from the source files:**

1. Copy the boundary files into `data/boundaries/`, matching the paths in `config/boundaries.toml`.
2. Load the boundaries and build the precinct-to-area tables. This takes about a minute.
   ```bash
   docker compose run --rm precinctmap precinctmap boundaries load
   ```
3. Add elections through the admin page, or with the app stopped:
   ```bash
   docker compose run --rm precinctmap precinctmap ingest data/samples/<file>.xlsx --review
   docker compose run --rm precinctmap precinctmap ingest --commit <staging_id>
   ```

### Property data

Load a new voter-file extract and parcel file with the app stopped:

```bash
docker compose run --rm precinctmap precinctmap addresses load data/samples/VOTERFILE.TXT --as-of YYYY-MM-DD --commit
docker compose run --rm precinctmap precinctmap parcels review data/samples/Parcel.csv --as-of YYYY-MM-DD
docker compose run --rm precinctmap precinctmap parcels commit <prc-id> --replace
```

From the voter file, only addresses, precincts and council districts are kept.

### Census data

Load a new ACS release with the app stopped. The steps and method are in `project-docs/census.md`.

```bash
docker compose run --rm precinctmap precinctmap census fetch --year 2024 --as-of YYYY-MM-DD
docker compose run --rm precinctmap precinctmap census load --year 2024 --as-of YYYY-MM-DD   # review
docker compose run --rm precinctmap precinctmap census load --year 2024 --as-of YYYY-MM-DD --commit
```

### Publishing a data release

After loading new data (an election, a parcel file, a census release), with the app stopped:

```bash
docker compose stop
docker compose run --rm precinctmap precinctmap bundle export --out data/dist
docker compose up -d
gh release create data-$(date +%F) data/dist/precinctmap-data.tar.gz data/dist/precinctmap-data.tar.gz.sha256 \
  --title "Data $(date +%F)" --notes-file data/dist/DATA.md
```

Export only from a stopped app. A store copied while the app runs can be missing its latest writes.

### When something changes

- **New precinct map from the Board of Elections:**
  1. Add the file under `data/boundaries/`.
  2. In `config/boundaries.toml`, give the current precinct set a `valid_to` date (the first election that uses the new map) and add the new set. Do the same for its municipality and ward sets.
  3. Run `precinctmap boundaries load --replace <changed set id>`. Results for every election are rebuilt and re-checked automatically.
- **An election date isn't recognized:** enter it on the admin page. To make it automatic for future files, add it to `src/precinctmap/catalog/calendar.py`.
- **A typo in a contest or candidate name:** add a reviewed fix to `src/precinctmap/ingest/corrections.py`. Then re-process the affected file: tick **Re-process** on the admin page, or use `--reprocess` on the command line.
- **A new spreadsheet layout:** the review stops with "no adapter recognizes this layout". A new adapter has to be written from a real sample; see `CLAUDE.md`.

### Checks

```bash
scripts/check.sh   # lint, type checks, Python and web tests, production build
```

The golden tests compare the database with the Board of Elections' published county totals. They run only when a local database exists and the app is stopped.

Developer notes are in `CLAUDE.md` and `project-docs/`. Status and next steps are in `NOTES.md`.

## License

MIT. See `LICENSE`.
