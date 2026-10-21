"""Review report: what the admin sees before approving a commit (CLAUDE.md data rule 5)."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from precinctmap.ingest.checks import BoundaryMatch, LongFormatCheck
from precinctmap.ingest.identify import ElectionIdentity
from precinctmap.ingest.model import ParsedFile
from precinctmap.ingest.votefor import VoteFor

Report = dict[str, Any]


@dataclass(frozen=True)
class ReviewInputs:
    staging_id: str
    filename: str
    sha256: str
    parsed: ParsedFile
    ident: ElectionIdentity
    vote_for: dict[int, VoteFor]
    long_check: LongFormatCheck
    match: BoundaryMatch
    contest_ids: dict[int, str]
    already_ingested: dict[str, str] | None
    reprocessing: dict[str, str] | None
    replaces: dict[str, Any] | None


def build_report(x: ReviewInputs) -> Report:
    blockers, warnings = _findings(x)
    status = "noop" if x.already_ingested else ("blocked" if blockers else "ready")
    return {
        "staging_id": x.staging_id,
        "filename": x.filename,
        "sha256": x.sha256,
        "adapter": f"{x.parsed.adapter} v{x.parsed.adapter_version}",
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "already_ingested": x.already_ingested,
        "reprocessing": x.reprocessing,
        "replaces": x.replaces,
        "election": _election(x.ident),
        "precincts": _precincts(x.parsed),
        "contests": _contests(x),
        "boundary_match": _match(x.match),
        "county_total_check": _county_check(x.parsed),
        "long_format_check": {
            "choices": x.long_check.choices,
            "result_rows": x.long_check.result_rows,
            "absent_cells": x.parsed.absent_cells,
            "failures": x.long_check.failures,
        },
        "normalizations": _normalizations(x.parsed),
    }


def _findings(x: ReviewInputs) -> tuple[list[str], list[str]]:
    blockers = list(x.ident.problems)
    if x.match.boundary_set_id is None and x.ident.election_date is not None:
        blockers.append(f"no precinct boundary set covers {x.ident.election_date}")
    bad_cols = [c for c in x.parsed.column_checks if not c.ok]
    if bad_cols:
        blockers.append(f"{len(bad_cols)} columns do not reconcile with the county-total row")
    if not x.long_check.ok:
        blockers.append(f"{len(x.long_check.failures)} choices lost votes in the long format")
    warnings = []
    if x.match.results_only:
        warnings.append(f"{len(x.match.results_only)} result precincts have no boundary")
    if x.match.retroactive:
        warnings.append("precinct boundaries are applied retroactively for this date")
    unknown = sum(1 for v in x.vote_for.values() if v.source == "unknown")
    if unknown:
        warnings.append(f"vote-for unknown for {unknown} contests (display only)")
    if x.parsed.out_of_county:
        warnings.append("file includes other counties' votes for joint contests (kept, not mapped)")
    if x.reprocessing:
        warnings.append("reprocess: commit replaces this already-ingested file's rows")
    if x.replaces:
        warnings.append(f"commit will supersede {x.replaces['filename']}")
    return blockers, warnings


def _election(ident: ElectionIdentity) -> dict[str, Any]:
    return {
        "election_id": ident.election_id,
        "county": ident.county,
        "date": ident.election_date.isoformat() if ident.election_date else None,
        "type": ident.election_type,
        "label": ident.label,
        "certified": ident.certified,
        "evidence": ident.evidence,
    }


def _precincts(p: ParsedFile) -> dict[str, Any]:
    by_county: Counter[str] = Counter()
    for o in p.out_of_county:
        by_county[o.county_name] += o.votes
    totals = {t.party: t for t in p.turnout}
    reg = sum(t.registered or 0 for t in p.turnout if t.party == "ALL")
    bal = sum(t.ballots_cast or 0 for t in p.turnout if t.party == "ALL")
    return {
        "rows": len(p.precincts),
        "registered": reg,
        "ballots_cast": bal,
        "turnout_parties": sorted(totals),
        "out_of_county_rows": p.out_of_county_names,
        "out_of_county_votes": dict(sorted(by_county.items())),
    }


def _contests(x: ReviewInputs) -> dict[str, Any]:
    on_ballot: dict[int, set[str]] = defaultdict(set)
    for r in x.parsed.results:
        on_ballot[r.contest_ordinal].add(r.precinct_name)
    listing = [
        {
            "ordinal": c.ordinal,
            "contest_id": x.contest_ids.get(c.ordinal),
            "party": c.party,
            "name": c.name_display,
            "type": c.contest_type,
            "vote_for": x.vote_for[c.ordinal].value,
            "vote_for_evidence": x.vote_for[c.ordinal].evidence,
            "precincts_on_ballot": len(on_ballot[c.ordinal]),
            "choices": [f"{ch.name_display} [{ch.kind}]" for ch in c.choices],
        }
        for c in x.parsed.contests
    ]
    return {
        "count": len(x.parsed.contests),
        "by_type": dict(Counter(c.contest_type for c in x.parsed.contests)),
        "by_party": dict(Counter(c.party or "nonpartisan" for c in x.parsed.contests)),
        "choices": sum(len(c.choices) for c in x.parsed.contests),
        "vote_for_inferred": sum(1 for v in x.vote_for.values() if v.source == "inferred"),
        "list": listing,
    }


def _match(m: BoundaryMatch) -> dict[str, Any]:
    return {
        "boundary_set_id": m.boundary_set_id,
        "retroactive": m.retroactive,
        "results_precincts": m.results_precincts,
        "matched": m.matched,
        "rate": m.rate,
        "results_only": m.results_only,
        "boundary_only": m.boundary_only,
    }


def _county_check(p: ParsedFile) -> dict[str, Any]:
    bad = [c for c in p.column_checks if not c.ok]
    return {
        "columns": len(p.column_checks),
        "passed": len(p.column_checks) - len(bad),
        "columns_with_out_of_county_votes": sum(1 for c in p.column_checks if c.out_of_county_sum),
        "failures": [
            f"{c.label}: precincts {c.precinct_sum} + other counties {c.out_of_county_sum}"
            f" != total {c.county_total}"
            for c in bad
        ],
    }


def _normalizations(p: ParsedFile) -> dict[str, Any]:
    by_kind: dict[str, list[str]] = defaultdict(list)
    for n in p.normalizations.entries:
        by_kind[n.kind].append(f"{n.location}: {n.before!r} -> {n.after!r}")
    return {
        "count": len(p.normalizations.entries),
        "by_kind": {k: len(v) for k, v in sorted(by_kind.items())},
        "examples": {k: v[:3] for k, v in sorted(by_kind.items())},
    }
