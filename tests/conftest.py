from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from precinctmap.config import Settings
from precinctmap.io.db import close_all, get_connection
from precinctmap.registry.blocks import load_blocks
from precinctmap.registry.config import load_config
from precinctmap.registry.crosswalk_build import build_crosswalks
from precinctmap.registry.loader import load_registry
from tests.fixtures.geo import CONFIG, write_mini_county


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(db_path=tmp_path / "t.duckdb", data_dir=tmp_path / "data", static_dir=None)


@pytest.fixture
def con(settings: Settings) -> Iterator[duckdb.DuckDBPyConnection]:
    yield get_connection(settings.db_path)
    close_all()


@pytest.fixture
def registry(con, settings, tmp_path):
    """Mini-county registry loaded with blocks and crosswalks (see tests/fixtures/geo.py)."""
    write_mini_county(settings.data_dir)
    path = tmp_path / "boundaries.toml"
    path.write_text(CONFIG)
    cfg = load_config(path)
    load_blocks(con, cfg.blocks, settings.data_dir, cfg.county)
    results = load_registry(con, cfg, settings.data_dir, set())
    build_crosswalks(con, cfg)
    return con, cfg, results


@pytest.fixture
def seeded(registry, settings, tmp_path):
    """Mini-county store with the 2025 general ingested and aggregated."""
    from precinctmap.aggregate.run import aggregate
    from precinctmap.ingest.commit import commit_staging
    from precinctmap.ingest.staging import stage_file
    from tests.fixtures.builders import mini_county_sheet

    con, _, _ = registry
    path = mini_county_sheet().write(tmp_path / "2025-General-Election_EXPORT_Official.xlsx")
    commit_staging(con, settings, stage_file(con, settings, path).staging_id)
    aggregate(con)
    return settings
