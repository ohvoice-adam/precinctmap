"""Identify which election a results file belongs to, from evidence only.

Evidence, in order: admin overrides (--election-date / --election-type), the year and type
words in the file name, and the content (party-ballot contests mean a primary). The date
comes from the override or the election calendar. Missing or conflicting evidence blocks
the file; it is never guessed.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from precinctmap.catalog import calendar
from precinctmap.catalog.calendar import ElectionType
from precinctmap.ingest.model import ParsedFile
from precinctmap.ingest.normalize import slug

_YEAR = re.compile(r"(?<!\d)(20\d\d)(?!\d)")
_TYPE_WORD = re.compile(r"(?i)(primary|general|special)")
_TYPES: dict[str, ElectionType] = {"primary": "primary", "general": "general", "special": "special"}


@dataclass
class ElectionIdentity:
    county: str
    election_date: date | None = None
    election_type: ElectionType | None = None
    certified: bool = False
    evidence: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def election_id(self) -> str | None:
        if self.election_date is None or self.election_type is None or self.problems:
            return None
        return f"{slug(self.county)}-{self.election_date.isoformat()}-{self.election_type}"

    @property
    def label(self) -> str:
        if self.election_date is None or self.election_type is None:
            return "unidentified election"
        d = self.election_date
        return f"{d.strftime('%B')} {d.day}, {d.year} {self.election_type}"


def content_type(parsed: ParsedFile) -> ElectionType:
    """'primary' when any contest is on a party ballot; otherwise 'general' (or special)."""
    return "primary" if any(c.party for c in parsed.contests) else "general"


def identify(
    filename: str,
    parsed: ParsedFile,
    override_date: date | None = None,
    override_type: ElectionType | None = None,
    override_certified: bool | None = None,
) -> ElectionIdentity:
    ident = ElectionIdentity(county=parsed.county)
    from_content = content_type(parsed)
    ident.evidence.append(
        f"content: {from_content} (party-ballot contests: "
        f"{sum(1 for c in parsed.contests if c.party)})"
    )
    m_type = _TYPE_WORD.search(filename)
    name_type = _TYPES[m_type.group(1).lower()] if m_type else None
    if name_type:
        ident.evidence.append(f"file name says {name_type}")
    ident.election_type = _resolve_type(ident, from_content, name_type, override_type)
    ident.election_date = _resolve_date(ident, filename, override_date)
    if ident.election_date and ident.election_type:
        listed = calendar.FRANKLIN_ELECTIONS.get(ident.election_date)
        if listed and listed != ident.election_type:
            ident.problems.append(
                f"calendar lists {ident.election_date} as {listed}, not {ident.election_type}"
            )
    if override_certified is not None:
        ident.certified = override_certified
        ident.evidence.append(f"certified={override_certified} (admin override)")
    else:
        ident.certified = "official" in filename.lower()
        ident.evidence.append(
            f"certified={ident.certified}"
            f" ('Official' {'in' if ident.certified else 'not in'} file name)"
        )
    return ident


def _resolve_type(
    ident: ElectionIdentity,
    from_content: ElectionType,
    name_type: ElectionType | None,
    override: ElectionType | None,
) -> ElectionType | None:
    chosen = override or name_type or from_content
    if override:
        ident.evidence.append(f"type override: {override}")
    is_primary = chosen == "primary"
    if is_primary != (from_content == "primary"):
        ident.problems.append(f"type {chosen} conflicts with content ({from_content})")
        return None
    if name_type and override and name_type != override:
        ident.problems.append(f"type override {override} conflicts with file name ({name_type})")
        return None
    return chosen


def _resolve_date(ident: ElectionIdentity, filename: str, override: date | None) -> date | None:
    if override:
        ident.evidence.append(f"date override: {override}")
        return override
    years = sorted({int(y) for y in _YEAR.findall(filename)})
    if len(years) != 1:
        ident.problems.append(
            "election date unknown: file name has no single year; pass --election-date"
        )
        return None
    if ident.election_type is None:
        return None
    hits = calendar.find(years[0], ident.election_type)
    if len(hits) != 1:
        ident.problems.append(
            f"calendar has {len(hits)} {ident.election_type} dates in {years[0]}; "
            "pass --election-date"
        )
        return None
    ident.evidence.append(f"date {hits[0]} from calendar ({years[0]} {ident.election_type})")
    return hits[0]
