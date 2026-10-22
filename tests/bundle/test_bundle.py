"""Data bundles: export the seeded mini-county store, load it into an empty one, compare."""

import json
import tarfile
from pathlib import Path

import pytest

from precinctmap.bundle.export import FORMAT, BundleError, export_bundle
from precinctmap.bundle.load import load_bundle
from precinctmap.config import Settings
from precinctmap.io.db import close_all, get_connection

COMPARED = ("precinct_results", "features", "census_blocks", "precinct_crosswalk", "geo_results")


@pytest.fixture
def exported(seeded, tmp_path):
    con = get_connection(seeded.db_path)
    archive = export_bundle(con, seeded, tmp_path / "dist")
    counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in COMPARED}
    votes = con.execute("SELECT sum(votes) FROM geo_results").fetchone()[0]
    return archive, counts, votes


def _fresh(tmp_path: Path) -> Settings:
    close_all()
    return Settings(
        db_path=tmp_path / "fresh" / "s.duckdb", data_dir=tmp_path / "fresh", static_dir=None
    )


def test_round_trip_into_an_empty_store_rebuilds_and_reconciles(exported, tmp_path):
    archive, counts, votes = exported
    fresh = _fresh(tmp_path)
    con = get_connection(fresh.db_path)
    summary = load_bundle(con, fresh, archive)
    assert summary.elections_reconciled == 1 and summary.sources == 1
    assert {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in COMPARED} == counts
    assert con.execute("SELECT sum(votes) FROM geo_results").fetchone()[0] == pytest.approx(votes)
    stored = Path(con.execute("SELECT stored_path FROM source_files").fetchone()[0])
    assert stored.exists() and stored.is_relative_to(fresh.data_dir)  # traceable on this machine


def test_notes_and_manifest_describe_vintage_and_where_to_update(exported):
    archive, _, _ = exported
    notes = (archive.parent / "DATA.md").read_text()
    assert "**Get updates:** https://www2.census.gov/programs-surveys/acs/summary_file/" in notes
    assert "November 4, 2025 general (certified)" in notes
    with tarfile.open(archive) as tar:
        manifest = json.loads(tar.extractfile(f"{FORMAT}/manifest.json").read())  # type: ignore[union-attr]
    assert "geo_results" not in manifest["tables"]  # rebuilt on load
    assert manifest["tables"]["precinct_results"]["rows"] > 0
    assert (
        (archive.parent / "precinctmap-data.tar.gz.sha256")
        .read_text()
        .endswith("precinctmap-data.tar.gz\n")
    )


def _repack(archive: Path, tmp_path: Path, edit) -> Path:
    work = tmp_path / "repack"
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    edit(work / FORMAT)
    out = tmp_path / "edited.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        tar.add(work / FORMAT, arcname=FORMAT)
    return out


def test_tampered_file_is_refused(exported, tmp_path):
    archive, _, _ = exported

    def tamper(root: Path) -> None:
        with (root / "tables" / "precinct_results.parquet").open("ab") as f:
            f.write(b"x")

    fresh = _fresh(tmp_path)
    with pytest.raises(BundleError, match="don't match the manifest"):
        load_bundle(get_connection(fresh.db_path), fresh, _repack(archive, tmp_path, tamper))


def test_newer_schema_is_refused(exported, tmp_path):
    archive, _, _ = exported

    def newer(root: Path) -> None:
        m = json.loads((root / "manifest.json").read_text())
        m["schema_version"] = 999
        (root / "manifest.json").write_text(json.dumps(m))

    fresh = _fresh(tmp_path)
    with pytest.raises(BundleError, match="newer than this software"):
        load_bundle(get_connection(fresh.db_path), fresh, _repack(archive, tmp_path, newer))


def test_a_store_with_data_is_refused(exported, seeded):
    archive, _, _ = exported
    with pytest.raises(BundleError, match="already has data"):
        load_bundle(get_connection(seeded.db_path), seeded, archive)
