"""ParsedFile -> DataFrames shaped exactly like the catalog tables, with stable ids.

contest_id = <election_id>:<party|np>:<slug(name)>; choice_id = <contest_id>:<slug(name)>.
Ids depend only on names, so a corrected file re-creates the same ids.
"""

from collections import Counter
from dataclasses import dataclass

import pandas as pd

from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.model import ParsedFile
from precinctmap.ingest.normalize import slug
from precinctmap.ingest.votefor import VoteFor


@dataclass(frozen=True)
class Tables:
    contests: pd.DataFrame
    choices: pd.DataFrame
    precinct_results: pd.DataFrame
    precinct_sources: pd.DataFrame
    precinct_turnout: pd.DataFrame
    out_of_county_results: pd.DataFrame
    normalization_log: pd.DataFrame

    def as_dict(self) -> dict[str, pd.DataFrame]:
        return dict(vars(self))


def _ids(parsed: ParsedFile, election_id: str) -> tuple[dict[int, str], dict[tuple[int, int], str]]:
    contest_ids: dict[int, str] = {}
    choice_ids: dict[tuple[int, int], str] = {}
    for c in parsed.contests:
        cid = f"{election_id}:{(c.party or 'np').lower()}:{slug(c.name_display)}"
        if cid in contest_ids.values():
            raise LayoutError(f"two contests normalize to the same id {cid!r}")
        contest_ids[c.ordinal] = cid
        seen: Counter[str] = Counter()
        for ch in c.choices:
            base = f"{cid}:{slug(ch.name_display)}"
            seen[base] += 1
            choice_ids[(c.ordinal, ch.ordinal)] = (
                base if seen[base] == 1 else f"{base}-{seen[base]}"
            )
    return contest_ids, choice_ids


def build_tables(
    parsed: ParsedFile, election_id: str, file_id: str, vote_for: dict[int, VoteFor]
) -> Tables:
    cids, chids = _ids(parsed, election_id)
    contests = pd.DataFrame(
        [
            {
                "contest_id": cids[c.ordinal],
                "election_id": election_id,
                "file_id": file_id,
                "source_ordinal": c.ordinal,
                "name_raw": c.name_raw,
                "name_display": c.name_display,
                "contest_type": c.contest_type,
                "party": c.party,
                "jurisdiction": c.jurisdiction,
                "vote_for": vote_for[c.ordinal].value,
                "vote_for_source": vote_for[c.ordinal].source,
            }
            for c in parsed.contests
        ]
    )
    choices = pd.DataFrame(
        [
            {
                "choice_id": chids[(c.ordinal, ch.ordinal)],
                "contest_id": cids[c.ordinal],
                "source_ordinal": ch.ordinal,
                "source_column": ch.column + 1,
                "source_sheet": ch.sheet or None,
                "name_raw": ch.name_raw,
                "name_display": ch.name_display,
                "party": ch.party,
                "choice_kind": ch.kind,
                "file_id": file_id,
            }
            for c in parsed.contests
            for ch in c.choices
        ]
    )
    return Tables(
        contests=contests.astype({"vote_for": "Int64"}),
        choices=choices.astype({"source_sheet": "string"}),  # all-NULL for one-sheet files
        precinct_results=_results(parsed, election_id, file_id, cids, chids),
        precinct_sources=_sources(parsed, election_id, file_id),
        precinct_turnout=_turnout(parsed, election_id, file_id),
        out_of_county_results=_out_of_county(parsed, election_id, file_id, cids, chids),
        normalization_log=_normalizations(parsed, file_id),
    )


def _results(
    parsed: ParsedFile,
    election_id: str,
    file_id: str,
    cids: dict[int, str],
    chids: dict[tuple[int, int], str],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "election_id": election_id,
            "precinct_name": [r.precinct_name for r in parsed.results],
            "contest_id": [cids[r.contest_ordinal] for r in parsed.results],
            "choice_id": [chids[(r.contest_ordinal, r.choice_ordinal)] for r in parsed.results],
            "votes": pd.array([r.votes for r in parsed.results], dtype="int64"),
            "file_id": file_id,
        }
    )


def _sources(parsed: ParsedFile, election_id: str, file_id: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "election_id": election_id,
                "precinct_name": p.name,
                "precinct_name_raw": p.name_raw,
                "precinct_code_raw": p.code_raw,
                "source_row": p.source_row,
                "file_id": file_id,
            }
            for p in parsed.precincts
        ]
    )


def _turnout(parsed: ParsedFile, election_id: str, file_id: str) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "election_id": election_id,
                "precinct_name": t.precinct_name,
                "party": t.party,
                "registered": t.registered,
                "ballots_cast": t.ballots_cast,
                "ballots_blank": t.ballots_blank,
                "file_id": file_id,
            }
            for t in parsed.turnout
        ]
    )
    return df.astype({"registered": "Int64", "ballots_cast": "Int64", "ballots_blank": "Int64"})


def _out_of_county(
    parsed: ParsedFile,
    election_id: str,
    file_id: str,
    cids: dict[int, str],
    chids: dict[tuple[int, int], str],
) -> pd.DataFrame:
    rows = [
        {
            "election_id": election_id,
            "county_name": o.county_name,
            "contest_id": cids[o.contest_ordinal],
            "choice_id": chids[(o.contest_ordinal, o.choice_ordinal)],
            "votes": o.votes,
            "file_id": file_id,
        }
        for o in parsed.out_of_county
    ]
    cols = ["election_id", "county_name", "contest_id", "choice_id", "votes", "file_id"]
    return pd.DataFrame(rows, columns=cols).astype({"votes": "int64"})


def _normalizations(parsed: ParsedFile, file_id: str) -> pd.DataFrame:
    cols = ["file_id", "kind", "location", "before", "after"]
    rows = [[file_id, n.kind, n.location, n.before, n.after] for n in parsed.normalizations.entries]
    return pd.DataFrame(rows, columns=cols)
