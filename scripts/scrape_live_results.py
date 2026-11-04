#!/usr/bin/env python3
"""Scrape unofficial live results from the Franklin County BOE site into an admin-loadable .xlsx.

Source: the JSON API behind https://vote.franklincountyohio.gov/elections/ (the same two
endpoints used in https://trevinflick.github.io/blog/posts/city-council-race-2025/):

  /api/precinct        entity tree: municipality (1) -> ward (2) -> precinct (3); `children` are
                       indices into the same array, and a precinct's array index is its area id
  /api/election/live   races -> choices -> per-precinct vectors (`votes` = election day,
                       `abs` = absentee, `prov` = provisional) aligned with the race's `areas`

Output is the existing `fcboe_wide_2025` layout (no new adapter): one row per precinct, a
`ZZZ`/`COUNTY TOTALS` row last, contests in sheet columns ending in OVER/UNDER VOTES.

Things the live feed does not carry, and what this script does about them:
  - over/under votes: written as 0 (shares exclude them anyway)
  - registered voters by party / blank ballots: omitted (only the ALL columns are required)
  - the COUNTY TOTALS row is the sum of the precinct rows, so the adapter's county-total check
    is self-consistent only; compare against the BOE's own totals page before committing
  - overlap-county votes (`overlapVotes`): not written; the script stops if any are non-zero

Nothing is committed. `--stage` uploads to the admin API for review (staging only); the
admin still approves and commits, as for any file. Re-scraping an election that already has a
committed file needs `replace` on commit, and `--reprocess` here if the same file is staged.

Usage:
  uv run python scripts/scrape_live_results.py --out data/raw          # write the .xlsx
  uv run python scripts/scrape_live_results.py --stage http://127.0.0.1:8000
      # needs PRECINCTMAP_ADMIN_USER / PRECINCTMAP_ADMIN_PASSWORD in the environment
"""

import argparse
import base64
import json
import logging
import os
import sys
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook

BASE = "https://vote.franklincountyohio.gov/elections/api"
USER_AGENT = "precinctmap election-results research (open source)"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COUNTY_NUMBER = 25  # Franklin
PARTIES = {"dem": "Dem", "rep": "Rep", "lib": "Lib", "grn": "Grn", "npc": "Npc", "opc": "OPC"}
log = logging.getLogger("scrape_live_results")


class ScrapeError(Exception):
    """The feed is not shaped the way this script expects."""


def fetch_json(path: str) -> dict[str, Any]:
    req = urllib.request.Request(f"{BASE}/{path}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data: dict[str, Any] = json.load(resp)
    except Exception:
        log.exception("fetching %s failed", path)
        raise
    return data


def precinct_names(entities: list[dict[str, Any]]) -> dict[int, str]:
    """Map area id -> precinct name like 'COLUMBUS 01-A'.

    Ids are 1-based positions in the entity list; `children` and race `areas` use the same ids.

    Two levels (parent -> precinct) give 'BLENDON-A'; three (parent -> ward -> precinct)
    give 'COLUMBUS 1-A'. The ingest normalizer pads the ward number.
    """
    names: dict[int, str] = {}
    for parent in (e for e in entities if e.get("type") == 1):
        base = str(parent["code"]).strip().upper()
        for ci in parent.get("children", []):
            child = entities[ci - 1]
            if child["type"] == 3:
                names[ci] = f"{base}-{child['code']}"
            elif child["type"] == 2:
                for pi in child.get("children", []):
                    if entities[pi - 1]["type"] != 3:
                        raise ScrapeError(f"entity {pi} under ward {ci} is not a precinct")
                    names[pi] = f"{base} {child['code']}-{entities[pi - 1]['code']}"
            else:
                raise ScrapeError(f"entity {ci} under {base} has type {child['type']}")
    if len(set(names.values())) != len(names):
        raise ScrapeError("duplicate precinct names built from the entity tree")
    return names


def contest_header(race: dict[str, Any], primary: bool) -> tuple[str, str]:
    """(column header, party code). Only primaries have party ballots; in a general the feed's
    race `party` is not a ballot party, so it is ignored."""
    party = str(race.get("party") or "").lower() if primary else ""
    if not party:
        return race["name"], "Non"
    if party not in PARTIES:
        raise ScrapeError(f"race {race['id']}: unknown party {party!r}")
    code = PARTIES[party]
    return f"{code} For {race['name']}", code


def build_rows(live: dict[str, Any], names: dict[int, str]) -> tuple[list[list[object]], int]:
    """Header rows 1-3 plus one data row per precinct (sorted by name). Returns (rows, n)."""
    order = sorted(names, key=lambda a: names[a])
    turnout = {t["area"]: t for t in live["turnout"]}
    missing = [names[a] for a in order if a not in turnout]
    if missing:
        raise ScrapeError(f"{len(missing)} precincts have no turnout row, e.g. {missing[:3]}")
    head1: list[object] = ["COUNTY NUMBER", "PRECINCT CODE", "PRECINCT NAME"]
    head1 += ["REGISTERED VOTERS TOTAL", "BALLOTS CAST TOTAL"]
    head2: list[object] = [None, None, None, None, None]
    head3: list[object] = [None, None, None, "VOTERS", "BALLOTS CAST"]
    rows: list[list[object]] = [
        [COUNTY_NUMBER, f"{i + 1:04d}", names[a], turnout[a]["reg"], _cast(turnout[a])]
        for i, a in enumerate(order)
    ]
    index = {a: i for i, a in enumerate(order)}
    for race in live["races"]:
        header, party = contest_header(race, bool(live.get("isPrimary")))
        _add_race(race, header, party, index, rows, (head1, head2, head3))
    return [head1, head2, head3, *rows], len(rows)


def _cast(t: dict[str, Any]) -> int:
    return int(t["abs"]) + int(t["day"]) + int(t["prov"])


def _add_race(
    race: dict[str, Any],
    header: str,
    party: str,
    index: dict[int, int],
    rows: list[list[object]],
    heads: tuple[list[object], list[object], list[object]],
) -> None:
    columns: list[tuple[str, dict[int, int]]] = []
    for ch in race["choices"]:
        if any(ch.get(k) for k in ("overlapVotes", "overlapAbs", "overlapProv")):
            raise ScrapeError(f"race {race['id']} {ch['name']!r}: overlap-county votes present")
        total = {
            a: int(ch["votes"][k]) + int(ch["abs"][k]) + int(ch["prov"][k])
            for k, a in enumerate(race["areas"])
            if a in index
        }
        columns.append((ch["name"], total))
    columns += [("OVER VOTES", {}), ("UNDER VOTES", {})]
    for label, per_area in columns:
        heads[0].append(header)
        heads[1].append(party)
        heads[2].append(label)
        for area, i in index.items():
            rows[i].append(per_area.get(area, 0))
    on_ballot = {a for a in race["areas"] if a in index}
    log.info(
        "race %s %r: %d precincts, %d choices",
        race["id"],
        race["name"],
        len(on_ballot),
        len(race["choices"]),
    )


def totals_row(rows: list[list[object]]) -> list[object]:
    data = rows[3:]
    width = len(rows[0])
    sums: list[object] = [COUNTY_NUMBER, "ZZZ", "COUNTY TOTALS"]
    sums += [sum(int(r[c]) for r in data) for c in range(3, width)]  # type: ignore[call-overload]
    return sums


def write_xlsx(rows: list[list[object]], path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Results"
    for r in [*rows, totals_row(rows)]:
        ws.append(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def stage(url: str, path: Path, election_date: str, election_type: str, reprocess: bool) -> None:
    """POST the file to the admin API (staging only) and print the review report."""
    user, pw = (
        os.environ.get("PRECINCTMAP_ADMIN_USER"),
        os.environ.get("PRECINCTMAP_ADMIN_PASSWORD"),
    )
    if not user or not pw:
        raise ScrapeError("set PRECINCTMAP_ADMIN_USER and PRECINCTMAP_ADMIN_PASSWORD to stage")
    boundary = uuid.uuid4().hex
    fields = {
        "election_date": election_date,
        "election_type": election_type,
        "certified": "false",
        "reprocess": str(reprocess).lower(),
    }
    body = b"".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, v in fields.items()
    )
    body += (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{path.name}"\r\nContent-Type: {XLSX}\r\n\r\n'
        ).encode()
        + path.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    req = urllib.request.Request(
        f"{url.rstrip('/')}/api/ingest",
        data=body,
        headers={
            "Authorization": f"Basic {token}",
            "X-PRECINCTMAP-Admin": "1",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.load(resp)
    print(result["report_text"])
    print(f"\nstaged as {result['staging_id']} (status {result['status']}); nothing is committed.")
    print(
        f"review it, then commit at {url.rstrip('/')}/admin "
        f"or: precinctmap ingest --commit {result['staging_id']}"
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("data/raw"), help="output directory")
    ap.add_argument("--stage", metavar="API_URL", help="also upload to this API for review")
    ap.add_argument(
        "--reprocess", action="store_true", help="with --stage: re-derive a staged file"
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    live = fetch_json("election/live")
    entities = fetch_json("precinct")["precincts"]
    if live.get("isTest"):
        raise ScrapeError("the feed is flagged isTest; refusing to export test data")
    election_date = f"{live['year']:04d}-{live['month']:02d}-{live['day']:02d}"
    election_type = "primary" if live.get("isPrimary") else "general"
    official = bool(live.get("isOfficial"))
    names = precinct_names(entities)
    rows, n = build_rows(live, names)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    label = "LIVE-Preliminary"  # never "official": identify.py reads that word as certified
    path = args.out / f"{election_date[:4]}-{election_type.title()}-Election_{label}_{stamp}.xlsx"
    write_xlsx(rows, path)
    print(
        f"{live.get('name')}: {election_date} {election_type}, {n} precincts, "
        f"{len(live['races'])} races, {len(rows[0]) - 5} result columns -> {path}"
    )
    if official:
        print("note: the feed says results are official; certified is NOT set here.")
    if args.stage:
        stage(args.stage, path, election_date, election_type, args.reprocess)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        log.exception("scrape failed")
        sys.exit(1)
