"""Parse `config/boundaries.toml`, the declarative boundary registry."""

import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

Geography = Literal["precinct", "council_district", "municipality", "ward", "zcta", "county"]
GEOGRAPHIES: tuple[Geography, ...] = (
    "precinct",
    "council_district",
    "municipality",
    "ward",
    "zcta",
    "county",
)
DEFAULT_CONFIG = Path("config/boundaries.toml")
LATER_FIELDS = frozenset({"code_field"})  # added 2026-10-21


class RegistryConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SetSpec:
    """One boundary set: read from a file, or derived from another set."""

    id: str
    geography: Geography
    valid_from: date
    valid_to: date | None = None
    native_from: date | None = None
    notes: str | None = None
    source: str | None = None  # relative to the data dir
    where: str | None = None
    id_field: str | None = None
    code_field: str | None = None  # source code kept in feature_codes (e.g. PRECINCTID)
    name_template: str | None = None
    jurisdiction: str | None = None
    clip_to_county: bool = False
    derive: str | None = None  # 'merge_precincts' | 'precinct_jurisdictions' | 'precinct_wards'
    derived_from: str | None = None
    merge: dict[str, list[str]] = field(default_factory=dict)
    places: str | None = None
    county_subdivisions: str | None = None
    carve_places: tuple[str, ...] = ()
    aliases: dict[str, str] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        """Stable dict used for the fingerprint.

        Fields added after the first registry load (LATER_FIELDS) are left out while unset,
        so adding a field to the schema never makes unchanged sets look changed.
        """
        out = {k: v for k, v in vars(self).items() if not (k in LATER_FIELDS and v is None)}
        for k in ("valid_from", "valid_to", "native_from"):
            out[k] = out[k].isoformat() if out[k] else None
        out["carve_places"] = list(self.carve_places)
        return out


@dataclass(frozen=True)
class BlocksSpec:
    source: str
    vintage: int
    id_field: str
    pop_field: str
    housing_field: str
    where: str | None = None


@dataclass(frozen=True)
class RegistryConfig:
    county: str
    blocks: BlocksSpec
    sets: tuple[SetSpec, ...]


def _set_spec(raw: dict[str, Any]) -> SetSpec:
    raw = dict(raw)
    raw["derived_from"] = raw.pop("from", None)
    raw["carve_places"] = tuple(raw.get("carve_places", ()))
    try:
        spec = SetSpec(**raw)
    except TypeError as exc:
        raise RegistryConfigError(f"set {raw.get('id')!r}: {exc}") from exc
    if spec.geography not in GEOGRAPHIES:
        raise RegistryConfigError(f"set {spec.id}: unknown geography {spec.geography!r}")
    if (spec.source is None) == (spec.derive is None):
        raise RegistryConfigError(f"set {spec.id}: give exactly one of source or derive")
    if spec.source and not spec.id_field:
        raise RegistryConfigError(f"set {spec.id}: file sources need id_field")
    if spec.valid_to and spec.valid_to <= spec.valid_from:
        raise RegistryConfigError(f"set {spec.id}: valid_to must be after valid_from")
    return spec


def load_config(path: Path = DEFAULT_CONFIG) -> RegistryConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    sets = tuple(_set_spec(s) for s in raw.get("sets", []))
    seen: set[str] = set()
    for s in sets:
        if s.id in seen:
            raise RegistryConfigError(f"duplicate set id {s.id}")
        if s.derived_from and s.derived_from not in seen:
            raise RegistryConfigError(f"set {s.id}: derives from {s.derived_from}, listed later")
        seen.add(s.id)
    return RegistryConfig(county=raw["county"], blocks=BlocksSpec(**raw["blocks"]), sets=sets)
