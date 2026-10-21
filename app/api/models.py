"""Response models: the API contract the web client is built against."""

from typing import Any

from pydantic import BaseModel


class Choice(BaseModel):
    choice_id: str
    name: str
    party: str | None
    kind: str


class CatalogContest(BaseModel):
    contest_id: str
    name: str
    party: str | None
    type: str
    vote_for: int | None
    jurisdiction: str | None
    precincts: int
    other_counties: list[str]
    choices: list[Choice]


class CatalogGeography(BaseModel):
    geography: str
    label: str
    boundary_set_id: str
    retroactive: bool


class CatalogElection(BaseModel):
    election_id: str
    date: str
    year: int
    type: str
    label: str
    certified: bool
    source_file: str | None
    turnout_parties: list[str]
    geographies: list[CatalogGeography]
    contests: list[CatalogContest]


class MeasureMetric(BaseModel):
    metric: str
    label: str
    kind: str  # count | share | currency | currency_delta | score | density
    description: str
    group: str
    universe: str | None = None  # what `n` counts (census measures)


class MeasureGeography(BaseModel):
    geography: str
    label: str


class MeasureCatalog(BaseModel):
    """An area-statistics dataset (auditor property, census demographics)."""

    dataset: str  # property | census
    label: str  # for the Data selector
    as_of: str
    source_file: str
    geographies: list[MeasureGeography]
    metrics: list[MeasureMetric]
    notes: list[str]


class Catalog(BaseModel):
    years: list[int]
    elections: list[CatalogElection]
    property: MeasureCatalog | None = None
    census: MeasureCatalog | None = None


class MeasureValue(BaseModel):
    value: float | None
    n: int  # parcels (property) or the universe estimate (census) the value rests on
    moe: float | None = None  # 90% margin of error (census)
    reliable: bool | None = None  # census: coefficient of variation <= 30%


class MeasureStats(BaseModel):
    dataset: str
    metric: str
    label: str
    kind: str
    description: str
    universe: str | None = None
    geography: str
    geography_label: str
    boundary_set_id: str
    as_of: str
    source_file: str
    notes: list[str]
    features: dict[str, MeasureValue]


class MeasureDetailMetric(BaseModel):
    metric: str
    label: str
    kind: str
    universe: str | None = None
    value: float | None
    n: int
    moe: float | None = None
    reliable: bool | None = None


class MeasureDetail(BaseModel):
    dataset: str
    feature_id: str
    name: str
    geography: str
    as_of: str
    source_file: str
    metrics: list[MeasureDetailMetric]
    grades: list[dict[str, Any]]


class ResultChoice(Choice):
    counts: bool  # counts toward valid votes (false for over / under votes)


class FeatureResult(BaseModel):
    v: list[float] | None  # votes per choice, in `choices` order; null = not on the ballot
    reg: float | None
    bal: float | None
    method: str | None = None
    pe: int | None = None  # precincts aggregated exactly
    pa: int | None = None  # precincts allocated


class Totals(BaseModel):
    valid_votes: float | None
    mapped: float | None
    excluded: float | None


class Results(BaseModel):
    election_id: str
    contest_id: str
    contest: str
    party: str | None
    type: str
    vote_for: int | None
    geography: str
    geography_label: str
    boundary_set_id: str
    retroactive: bool
    source_file: str
    choices: list[ResultChoice]
    totals: Totals
    notes: list[str]
    features: dict[str, FeatureResult]


class DetailChoice(ResultChoice):
    votes: float
    share: float | None


class Contribution(BaseModel):
    precinct: str
    split_share: float
    method: str
    weight_basis: str
    precinct_valid_votes: int | None


class Turnout(BaseModel):
    registered: float | None
    ballots_cast: float | None
    turnout: float | None


class Detail(BaseModel):
    feature_id: str
    name: str
    jurisdiction: str | None
    contest: str
    geography: str
    boundary_set_id: str
    retroactive: bool
    on_ballot: bool
    valid_votes: float
    choices: list[DetailChoice]
    method: str | None
    contributions: list[Contribution]
    turnout: Turnout | None
    source_file: str
    source_sha256: str


class Staged(BaseModel):
    staging_id: str
    status: str
    report: dict[str, Any]  # the full review report (see precinctmap.ingest.report)
    report_text: str


class Committed(BaseModel):
    action: str
    election_id: str
    detail: str
    reconciliation: list[dict[str, Any]]
