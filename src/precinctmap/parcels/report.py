"""Parcel review report: coverage by method, voter-file agreement, and every exception."""

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

Report = dict[str, Any]


def _counts(series: Any) -> dict[str, int]:
    return {str(k): int(v) for k, v in series.value_counts(dropna=False).items()}


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 6) if d else None


def _voter_section(f: Any, read: Any, addr: tuple[str, date] | None) -> dict[str, Any]:
    matched = f[f["voter_match"]]
    pclass = dict(zip(read.frame["pid"], read.frame["pclass"], strict=True))
    residential = f[f["pid"].map(pclass).eq("R")]
    disagree = f[f["precinct_agrees"].eq(False)]
    site = dict(zip(read.frame["pid"], read.frame["site_address"], strict=True))
    compared = int(f["council_agrees"].notna().sum())
    return {
        "address_file_id": addr[0] if addr else None,
        "address_as_of": addr[1].isoformat() if addr else None,
        "matched": len(matched),
        "match_rate": _rate(len(matched), len(f)),
        "residential_match_rate": _rate(int(residential["voter_match"].sum()), len(residential)),
        "precinct_agreement": _rate(int(matched["precinct_agrees"].eq(True).sum()), len(matched)),
        "precinct_disagreements": len(disagree),
        "council_compared": compared,
        "council_agreement": _rate(int(f["council_agrees"].eq(True).sum()), compared),
        "examples": [
            f"{p} {site.get(p, '')}: geometry {g} -> voter file {v} (voter file used)"
            for p, g, v in disagree[["pid", "geometry_precinct", "voter_precinct"]]
            .head(15)
            .itertuples(index=False)
        ],
    }


def _retroactive(con: duckdb.DuckDBPyConnection, set_id: str, as_of: date) -> bool:
    row = con.execute(
        "SELECT native_from FROM boundary_sets WHERE boundary_set_id = ?", [set_id]
    ).fetchone()
    return bool(row and row[0] and as_of < row[0])


def build_report(
    con: duckdb.DuckDBPyConnection,
    staging_id: str,
    path: Path,
    sha: str,
    as_of: date,
    read: Any,
    result: Any,
    addr: tuple[str, date] | None,
    already: bool,
) -> Report:
    f = result.frame
    log = Counter(issue for _, issue, _ in read.log + result.log)
    columbus = f[f["council_method"] != "not_in_columbus"]
    unassigned = int((f["precinct_method"] == "unassigned").sum())
    warnings = []
    if addr is None:
        warnings.append("no voter-address table loaded: no cross-check or address fallback")
    if unassigned:
        warnings.append(f"{unassigned} parcels have no precinct")
    return {
        "staging_id": staging_id,
        "filename": path.name,
        "sha256": sha,
        "as_of": as_of.isoformat(),
        "status": "noop" if already else "ready",
        "warnings": warnings,
        "rows": {
            "read": read.rows_read,
            "kept": len(read.frame),
            "repaired": log["repaired_row"],
            "rejected": log["rejected_row"],
            "bad_coordinates": log["bad_coordinates"],
        },
        "precinct": {
            "boundary_set_id": result.precinct_set_id,
            "retroactive": _retroactive(con, result.precinct_set_id, as_of),
            "methods": _counts(f["precinct_method"]),
            "assigned": int(f["precinct_name"].notna().sum()),
            "parcels": len(f),
        },
        "council": {
            "boundary_set_id": result.council_set_id,
            "columbus_parcels": len(columbus),
            "methods": _counts(f["council_method"]),
            "assigned": int(columbus["council_district"].notna().sum()),
        },
        "voter_check": _voter_section(f, read, addr),
        "log": dict(log),
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2%}"


def render(r: Report) -> str:
    rows, p, c, v = r["rows"], r["precinct"], r["council"], r["voter_check"]
    lines = [
        f"Parcel review {r['staging_id']}: {r['filename']} (as of {r['as_of']})",
        f"  STATUS: {r['status'].upper()}",
        *[f"  warning: {w}" for w in r["warnings"]],
        "",
        f"Rows: read {rows['read']:,}, kept {rows['kept']:,}, repaired {rows['repaired']:,}, "
        f"rejected {rows['rejected']:,}, bad coordinates {rows['bad_coordinates']:,}",
        f"Precinct ({p['boundary_set_id']}{', retroactive' if p['retroactive'] else ''}): "
        f"{p['assigned']:,}/{p['parcels']:,} assigned; methods {p['methods']}",
        f"Council district ({c['boundary_set_id']}): {c['assigned']:,}/{c['columbus_parcels']:,} "
        f"Columbus parcels assigned; methods {c['methods']}",
        f"Voter-file cross-check (addresses as of {v['address_as_of']}): matched {v['matched']:,} "
        f"({_pct(v['match_rate'])}; residential {_pct(v['residential_match_rate'])})",
        f"  precinct agreement {_pct(v['precinct_agreement'])}"
        f" ({v['precinct_disagreements']:,} overridden by the voter file); "
        f"council agreement {_pct(v['council_agreement'])} of {v['council_compared']:,}",
        *[f"    {e}" for e in v["examples"]],
        "",
        f"Log entries: {r['log']}",
    ]
    return "\n".join(lines) + "\n"
