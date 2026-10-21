from datetime import date

import pytest

from precinctmap.catalog.migrate import MigrationError, apply_migrations
from precinctmap.catalog.queries import contests_summary, elections_summary
from precinctmap.ingest.commit import commit_staging
from precinctmap.ingest.errors import StagingError
from precinctmap.ingest.staging import stage_file
from precinctmap.registry.config import SetSpec
from precinctmap.registry.loader import load_set
from precinctmap.registry.store import set_for
from tests.fixtures.builders import precinct_shapefile, sheet_2024, sheet_2025

NAMES = ["COLUMBUS 01-A", "BEXLEY 01-A", "BLENDON-A", "OBETZ-D"]
GENERAL = "2025-General-Election_EXPORT_Official.xlsx"


@pytest.fixture
def with_precincts(con, settings):
    folder = settings.data_dir / "boundaries"
    folder.mkdir(parents=True)
    precinct_shapefile(folder / "p.shp", NAMES)
    spec = SetSpec(
        id="pset",
        geography="precinct",
        source="boundaries/p.shp",
        id_field="NAME",
        valid_from=date(2024, 1, 1),
        native_from=date(2025, 7, 30),
    )
    load_set(con, spec, settings.data_dir, "Franklin", replace=False)
    return con


def _count(con, sql, params=()):
    return con.execute(sql, list(params)).fetchone()[0]


def test_precinct_set_lookup_marks_retroactive(with_precincts):
    early = set_for(with_precincts, "precinct", "Franklin", date(2024, 11, 5))
    late = set_for(with_precincts, "precinct", "Franklin", date(2025, 11, 4))
    assert early is not None and early.retroactive
    assert late is not None and not late.retroactive
    assert set_for(with_precincts, "precinct", "Franklin", date(2023, 11, 7)) is None


def test_review_reports_match_and_checks_then_commit_lands_every_row(
    with_precincts, settings, tmp_path
):
    con = with_precincts
    staged = stage_file(con, settings, sheet_2025().write(tmp_path / GENERAL))
    r = staged.report
    assert r["status"] == "ready", r["blockers"]
    assert r["boundary_match"]["matched"] == 3 and r["boundary_match"]["rate"] == 1.0
    assert r["boundary_match"]["boundary_only"] == ["OBETZ-D"]
    assert r["county_total_check"]["passed"] == 11
    assert r["long_format_check"]["failures"] == []
    assert (staged.directory / "report.txt").exists()
    assert _count(con, "SELECT count(*) FROM precinct_results") == 0  # review never commits

    result = commit_staging(con, settings, staged.staging_id)
    assert result.action == "commit"
    assert _count(con, "SELECT count(*) FROM precinct_results") == 16
    assert _count(con, "SELECT sum(votes) FROM out_of_county_results") == 16
    assert _count(con, "SELECT count(*) FROM unmatched_precincts WHERE side='boundary_only'") == 1
    assert _count(con, "SELECT count(*) FROM normalization_log") > 0
    (row,) = elections_summary(con)
    assert (row["precincts"], row["contests"], row["matched"]) == (3, 2, 3)
    levy = next(
        c for c in contests_summary(con, row["election_id"]) if c["contest_type"] == "issue"
    )
    assert levy["votes"] == 115 + 60  # yes + no in Franklin precincts; over/under excluded


def test_same_file_twice_is_a_noop(with_precincts, settings, tmp_path):
    path = sheet_2025().write(tmp_path / GENERAL)
    first = stage_file(with_precincts, settings, path)
    commit_staging(with_precincts, settings, first.staging_id)
    again = stage_file(with_precincts, settings, path)
    assert again.report["status"] == "noop"
    assert commit_staging(with_precincts, settings, first.staging_id).action == "noop"
    assert _count(with_precincts, "SELECT count(*) FROM source_files") == 1


def test_corrected_file_supersedes_predecessor(with_precincts, settings, tmp_path):
    con = with_precincts
    old = stage_file(con, settings, sheet_2025().write(tmp_path / GENERAL))
    commit_staging(con, settings, old.staging_id)
    fixed_path = tmp_path / "fixed" / GENERAL
    fixed_path.parent.mkdir()
    new = stage_file(con, settings, sheet_2025(zoo_extra=7).write(fixed_path))
    assert new.report["replaces"]["filename"] == GENERAL
    with pytest.raises(StagingError, match="would replace"):
        commit_staging(con, settings, new.staging_id)  # replacing needs explicit confirmation
    assert _count(con, "SELECT count(*) FROM source_files") == 1
    commit_staging(con, settings, new.staging_id, allow_replace=True)
    statuses = con.execute("SELECT status FROM source_files ORDER BY status").fetchall()
    assert statuses == [("active",), ("superseded",)]
    assert _count(con, "SELECT count(DISTINCT file_id) FROM precinct_results") == 1
    assert (
        _count(
            con, "SELECT sum(votes) FROM precinct_results WHERE choice_id LIKE '%:for-the-tax-levy'"
        )
        == 122
    )
    assert _count(con, "SELECT count(*) FROM ingest_events WHERE action = 'supersede'") == 1


def test_blocked_review_cannot_commit(with_precincts, settings, tmp_path):
    staged = stage_file(with_precincts, settings, sheet_2024().write(tmp_path / "Results.xlsx"))
    assert staged.report["status"] == "blocked"
    with pytest.raises(StagingError, match="blocked"):
        commit_staging(with_precincts, settings, staged.staging_id)
    ok = stage_file(
        with_precincts, settings, tmp_path / "Results.xlsx", override_date=date(2024, 11, 5)
    )
    assert ok.report["status"] == "ready"
    assert ok.report["boundary_match"]["retroactive"] is True


def test_reconciliation_failure_blocks(with_precincts, settings, tmp_path):
    sheet = sheet_2025()
    sheet.total_overrides[7] = 999
    staged = stage_file(with_precincts, settings, sheet.write(tmp_path / GENERAL))
    assert staged.report["status"] == "blocked"
    assert any("county-total" in b for b in staged.report["blockers"])


def test_missing_boundary_set_blocks(con, settings, tmp_path):
    staged = stage_file(con, settings, sheet_2025().write(tmp_path / GENERAL))
    assert any("no precinct boundary set" in b for b in staged.report["blockers"])


def test_changed_migration_is_rejected(con):
    con.execute("UPDATE schema_migrations SET sha256 = 'tampered' WHERE version = 1")
    with pytest.raises(MigrationError, match="changed after it was applied"):
        apply_migrations(con)


def test_unknown_staging_id(con, settings):
    with pytest.raises(StagingError, match="no staging batch"):
        commit_staging(con, settings, "stg-missing")


def test_reprocess_rederives_rows_and_updates_certified(with_precincts, settings, tmp_path):
    con = with_precincts
    path = sheet_2025().write(tmp_path / "2025-General-Election.xlsx")  # no 'Official'
    commit_staging(con, settings, stage_file(con, settings, path).staging_id)
    assert _count(con, "SELECT count(*) FROM elections WHERE certified") == 0
    again = stage_file(con, settings, path, override_certified=True, reprocess=True)
    assert again.report["status"] == "ready"
    assert again.report["reprocessing"]["status"] == "active"
    result = commit_staging(con, settings, again.staging_id)
    assert result.action == "commit"
    assert _count(con, "SELECT count(*) FROM elections WHERE certified") == 1
    assert _count(con, "SELECT count(*) FROM source_files") == 1
    assert _count(con, "SELECT count(*) FROM precinct_results") == 16
    assert _count(con, "SELECT count(*) FROM ingest_events WHERE action = 'reprocess'") == 1


def test_reprocess_requires_an_ingested_file(with_precincts, settings, tmp_path):
    path = sheet_2025().write(tmp_path / GENERAL)
    with pytest.raises(StagingError, match="needs an active ingested file"):
        stage_file(with_precincts, settings, path, reprocess=True)


def test_committed_batch_missing_from_the_store_is_an_error(with_precincts, settings, tmp_path):
    """A staging folder copied from another machine must not pass for a loaded election."""
    staged = stage_file(with_precincts, settings, sheet_2025().write(tmp_path / GENERAL))
    commit_staging(with_precincts, settings, staged.staging_id)
    with_precincts.execute("DELETE FROM source_files")  # this store never loaded it
    with pytest.raises(StagingError, match="marked committed, but this store doesn't have"):
        commit_staging(with_precincts, settings, staged.staging_id)
