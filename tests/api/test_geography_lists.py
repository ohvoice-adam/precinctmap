"""Every geography the pipeline materializes must be labeled, ordered and servable."""

from precinctmap.aggregate.materialize import GEOGRAPHIES
from precinctmap.registry.config import GEOGRAPHIES as CONFIG_GEOGRAPHIES
from precinctmap.registry.crosswalk_build import TARGET_GEOGRAPHIES
from precinctmap.serve.catalog import GEOGRAPHY_ORDER
from precinctmap.serve.geo import SERVABLE, _notes
from precinctmap.serve.labels import (
    GEOGRAPHY_LABELS,
    RETROACTIVE_STATE_DISTRICTS,
    STATE_DISTRICT_NOTE,
)


def test_materialized_geographies_are_labeled_ordered_and_servable():
    assert set(GEOGRAPHIES) == set(GEOGRAPHY_ORDER)
    for geo in GEOGRAPHIES:
        assert geo in GEOGRAPHY_LABELS
        assert geo in SERVABLE
        assert geo in CONFIG_GEOGRAPHIES
    assert set(TARGET_GEOGRAPHIES) == set(GEOGRAPHIES) - {"precinct"}


def test_state_district_geo_notes_say_franklin_portion_and_retroactive():
    for geo in ("state_house", "state_senate"):
        assert _notes(geo, False) == [STATE_DISTRICT_NOTE]
        assert _notes(geo, True) == [STATE_DISTRICT_NOTE, RETROACTIVE_STATE_DISTRICTS]
    assert "Franklin County part" in STATE_DISTRICT_NOTE
