from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from precinctmap.registry.config import RegistryConfigError, load_config
from precinctmap.registry.derive import precinct_ward
from precinctmap.registry.loader import load_registry, load_set
from precinctmap.registry.store import BoundaryError, read_features, set_for
from tests.fixtures.geo import CONFIG


def _xw(con, pset, tset):
    rows = con.execute(
        "SELECT precinct_name, feature_id, split_share, method, weight_basis"
        " FROM precinct_crosswalk"
        " WHERE precinct_set_id = ? AND target_set_id = ? ORDER BY 1, 2",
        [pset, tset],
    ).fetchall()
    return {(p, f): (round(s, 4), m, w) for p, f, s, m, w in rows}  # CRS round-trip slivers


def test_real_registry_config_parses():
    cfg = load_config(Path("config/boundaries.toml"))
    assert cfg.sets[0].geography == "county"  # clip mask loads first
    assert {s.geography for s in cfg.sets} == {
        "county",
        "precinct",
        "municipality",
        "council_district",
        "ward",
        "zcta",
    }
    retro = next(s for s in cfg.sets if s.id.endswith("precincts-2025-07-retro"))
    assert retro.valid_to == date(2025, 7, 30) and retro.merge["HAMILTON-A"] == [
        "HAMILTON-A",
        "OBETZ-D",
    ]


def test_config_rejects_parent_listed_later(tmp_path):
    bad = CONFIG.replace('from = "pct"\nmerge', 'from = "muni"\nmerge')
    (tmp_path / "b.toml").write_text(bad)
    with pytest.raises(RegistryConfigError, match="listed later"):
        load_config(tmp_path / "b.toml")


def test_retro_precincts_merge_obetz_d_into_hamilton_a(registry):
    con, _, _ = registry
    retro = read_features(con, "pct-retro").set_index("feature_id")
    assert "OBETZ-D" not in retro.index and len(retro) == 4
    native = read_features(con, "pct").set_index("feature_id").to_crs(3735)
    merged = retro.to_crs(3735).loc["HAMILTON-A"].geometry.area
    assert merged == pytest.approx(native.loc[["HAMILTON-A", "OBETZ-D"]].area.sum())


def test_set_lookup_by_date_and_retroactive_flag(registry):
    con, _, _ = registry
    early = set_for(con, "precinct", "Franklin", date(2024, 11, 5))
    late = set_for(con, "precinct", "Franklin", date(2025, 11, 4))
    assert early is not None and early.boundary_set_id == "pct-retro" and early.retroactive
    assert late is not None and late.boundary_set_id == "pct" and not late.retroactive
    assert set_for(con, "precinct", "Franklin", date(2023, 11, 7)) is None


def test_municipalities_named_from_tiger_and_village_carved(registry):
    con, _, _ = registry
    muni = read_features(con, "muni").set_index("feature_id")
    assert dict(zip(muni["name"], muni["jurisdiction"], strict=True)) == {
        "Columbus": "city",
        "Blendon Township": "township",
        "Hamilton Township": "township",
        "Obetz": "city",
        "Brice": "village",
    }
    retro = read_features(con, "muni-retro")
    assert "Obetz" not in set(retro["name"])  # OBETZ-D area belonged to Hamilton Township then


def test_council_crosswalk_exact_allocated_and_excluded(registry):
    con, _, _ = registry
    xw = _xw(con, "pct", "council")
    assert xw[("COLUMBUS 01-A", "1")] == (1.0, "exact", "population")
    assert xw[("COLUMBUS 01-B", "1")] == (0.3, "allocated", "population")
    assert xw[("COLUMBUS 01-B", "2")] == (0.7, "allocated", "population")
    assert not any(p == "BLENDON-A" for p, _ in xw)
    excluded = con.execute(
        "SELECT count(*) FROM crosswalk_log WHERE target_set_id = 'council' AND issue = 'excluded'"
        " AND precinct_set_id = 'pct'"
    ).fetchone()[0]
    assert excluded == 3


def test_municipality_crosswalk_allocates_only_village_hosts(registry):
    con, _, _ = registry
    xw = _xw(con, "pct", "muni")
    assert xw[("COLUMBUS 01-B", "columbus")] == (1.0, "exact", "jurisdiction")
    assert xw[("BLENDON-A", "blendon-township")] == (0.9, "allocated", "population")
    assert xw[("BLENDON-A", "brice")] == (0.1, "allocated", "population")


def test_reload_is_unchanged_and_changes_need_replace(registry, settings):
    con, cfg, first = registry
    assert {r.action for r in first} == {"loaded"}
    again = load_registry(con, cfg, settings.data_dir, set())
    assert {r.action for r in again} == {"unchanged"}
    council = next(s for s in cfg.sets if s.id == "council")
    moved = replace(council, valid_from=date(2023, 5, 2))
    with pytest.raises(BoundaryError, match="--replace council"):
        load_set(con, moved, settings.data_dir, cfg.county, replace=False)
    assert load_set(con, moved, settings.data_dir, cfg.county, replace=True).action == "replaced"
    gone = con.execute(
        "SELECT count(*) FROM precinct_crosswalk WHERE target_set_id = 'council'"
    ).fetchone()[0]
    assert gone == 0  # crosswalks on a replaced set are dropped until rebuilt


def test_real_config_covers_any_earlier_election_date():
    """Every geography has exactly one set for pre-2024 dates (decision 2026-10-22)."""
    from datetime import date

    from precinctmap.registry.config import DEFAULT_CONFIG, load_config

    cfg = load_config(DEFAULT_CONFIG)
    for on in (date(2016, 11, 8), date(2022, 11, 8), date(2024, 11, 5), date(2026, 11, 3)):
        for geo in ("county", "precinct", "municipality", "council_district", "zcta"):
            covering = [
                s.id
                for s in cfg.sets
                if s.geography == geo
                and s.valid_from <= on
                and (s.valid_to is None or on < s.valid_to)
            ]
            assert len(covering) == 1, (geo, on, covering)


def test_precinct_ward_prefix():
    assert precinct_ward("COLUMBUS 01-A") == ("COLUMBUS", "01")
    assert precinct_ward("MARBLE CLIFF-A") == ("MARBLE CLIFF", None)
    with pytest.raises(BoundaryError, match="ward prefix"):
        precinct_ward("COLUMBUS 01")


def test_wards_dissolve_precincts_by_prefix_and_nest_exactly(registry):
    con, _, _ = registry
    names = dict(read_features(con, "ward")[["feature_id", "name"]].values)
    assert names == {
        "columbus-ward-01": "Columbus Ward 01",
        "blendon-township": "Blendon Township",
        "hamilton-township": "Hamilton Township",
        "obetz": "Obetz",
    }
    xw = _xw(con, "pct-retro", "ward-retro")
    assert set(xw) == {
        ("COLUMBUS 01-A", "columbus-ward-01"),
        ("COLUMBUS 01-B", "columbus-ward-01"),
        ("BLENDON-A", "blendon-township"),
        ("HAMILTON-A", "hamilton-township"),  # includes the old OBETZ-D
    }
    assert {v for v in xw.values()} == {(1.0, "exact", "jurisdiction")}
