"""Plain-text rendering of a review report for the CLI and report.txt."""

from typing import Any

from precinctmap.ingest.report import Report


def _list(items: list[str], limit: int) -> str:
    if not items:
        return "none"
    shown = ", ".join(items[:limit])
    return shown + (f", ... (+{len(items) - limit} more)" if len(items) > limit else "")


def _header(r: Report) -> list[str]:
    e = r["election"]
    lines = [
        f"Review {r['staging_id']}: {r['filename']}",
        f"  sha256 {r['sha256'][:16]}...  layout {r['adapter']}",
        f"  STATUS: {r['status'].upper()}",
    ]
    lines += [f"  BLOCKER: {b}" for b in r["blockers"]]
    lines += [f"  warning: {w}" for w in r["warnings"]]
    if r["already_ingested"]:
        lines.append(f"  already ingested as {r['already_ingested']}; commit is a no-op")
    lines += [
        "",
        f"Election: {e['label']}  ({e['election_id'] or 'no id until identified'})",
        f"  county {e['county']}, certified {'yes' if e['certified'] else 'no'}",
    ]
    lines += [f"  evidence: {ev}" for ev in e["evidence"]]
    return lines


def _body(r: Report) -> list[str]:
    p, c, m = r["precincts"], r["contests"], r["boundary_match"]
    ct, lf = r["county_total_check"], r["long_format_check"]
    rate = f"{m['rate']:.1%}" if m["rate"] is not None else "n/a"
    ooc = ", ".join(f"{k} {v:,}" for k, v in p["out_of_county_votes"].items()) or "none"
    return [
        "",
        f"Precincts: {p['rows']}  registered {p['registered']:,}  ballots {p['ballots_cast']:,}"
        f"  turnout parties {', '.join(p['turnout_parties'])}",
        f"  out-of-county rows: {_list(p['out_of_county_rows'], 20)}",
        f"  out-of-county votes (kept, never mapped): {ooc}",
        f"Contests: {c['count']} {c['by_type']}  by party {c['by_party']}  choices {c['choices']}",
        f"  vote-for inferred for {c['vote_for_inferred']}/{c['count']}",
        "",
        f"Precinct match: set {m['boundary_set_id'] or 'NONE'}"
        f"{' (retroactive)' if m['retroactive'] else ''}"
        f"  matched {m['matched']}/{m['results_precincts']} ({rate})",
        f"  unmatched result precincts: {_list(m['results_only'], 30)}",
        f"  boundary precincts with no results: {_list(m['boundary_only'], 30)}",
        "",
        f"County-total check: {ct['passed']}/{ct['columns']} columns reconcile"
        f" ({ct['columns_with_out_of_county_votes']} include other counties' votes)",
        *[f"  FAIL {f}" for f in ct["failures"][:20]],
        f"Long-format check: {lf['choices'] - len(lf['failures'])}/{lf['choices']} choices"
        f" re-total exactly; {lf['result_rows']:,} result rows;"
        f" {lf['absent_cells']:,} precinct x contest cells not on the ballot",
        *[f"  FAIL {f}" for f in lf["failures"][:20]],
        "",
        f"Normalizations: {r['normalizations']['count']} {r['normalizations']['by_kind']}",
        *[
            f"  {kind}: {ex}"
            for kind, exs in r["normalizations"]["examples"].items()
            for ex in exs[:2]
        ],
    ]


def _contest_line(k: dict[str, Any]) -> str:
    vf = f"vote for {k['vote_for']}" if k["vote_for"] else "vote for ?"
    party = k["party"] or "-"
    return (
        f"  {k['ordinal']:>3} {party:<4} {k['type']:<9} {vf:<11} {k['precincts_on_ballot']:>4} pct"
        f"  {k['name']}  [{len(k['choices'])} choices]"
    )


def render(r: Report, contest_limit: int | None = None) -> str:
    """Whole report; `contest_limit` truncates the per-contest listing (None = all)."""
    contests = r["contests"]["list"]
    shown = contests if contest_limit is None else contests[:contest_limit]
    lines = _header(r) + _body(r) + ["", "Contests (ordinal, party, type, vote-for, precincts):"]
    lines += [_contest_line(k) for k in shown]
    if len(shown) < len(contests):
        lines.append(f"  ... {len(contests) - len(shown)} more in report.txt")
    if r["replaces"]:
        lines += ["", f"Replaces: {r['replaces']}"]
    return "\n".join(lines) + "\n"
