from pathlib import Path

from typer.testing import CliRunner

from precinctmap import __version__
from precinctmap.cli import app
from precinctmap.config import load_settings


def test_settings_defaults_put_db_under_data_dir():
    s = load_settings({})
    assert s.data_dir == Path("data")
    assert s.db_path == Path("data/precinctmap.duckdb")
    assert s.static_dir is None


def test_settings_read_env_overrides():
    s = load_settings({"PRECINCTMAP_DATA_DIR": "/srv/d", "PRECINCTMAP_STATIC_DIR": "/srv/web"})
    assert s.db_path == Path("/srv/d/precinctmap.duckdb")
    assert s.static_dir == Path("/srv/web")


def test_cli_catalog_on_empty_store(tmp_path, monkeypatch):
    monkeypatch.setenv("PRECINCTMAP_DB_PATH", str(tmp_path / "empty.duckdb"))
    result = CliRunner().invoke(app, ["catalog"])
    assert result.exit_code == 0, result.output
    assert "catalog is empty" in result.stdout


def test_cli_ingest_requires_exactly_one_mode():
    result = CliRunner().invoke(app, ["ingest"])
    assert result.exit_code != 0
    assert "exactly one of --review" in result.output


def test_cli_version_prints_package_version():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
    assert __version__ != "0.0.0+unknown"
