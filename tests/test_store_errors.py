"""An unusable data folder fails with a clear message (library) and a 503 (API, health)."""

import os

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from precinctmap.config import Settings
from precinctmap.io.db import StoreUnavailableError, close_all, get_connection

pytestmark = pytest.mark.skipif(os.getuid() == 0, reason="root can write anywhere")


@pytest.fixture
def locked_dir(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    folder.chmod(0o500)  # like a root-owned ./data seen by the container's user
    yield folder
    folder.chmod(0o700)
    close_all()


def test_unwritable_folder_names_the_fix(locked_dir):
    with pytest.raises(StoreUnavailableError, match="must exist and be writable") as exc:
        get_connection(locked_dir / "store.duckdb")
    assert "PRECINCTMAP_UID" in str(exc.value) and str(locked_dir) in str(exc.value)


def test_api_and_health_report_503_with_the_reason(locked_dir):
    settings = Settings(db_path=locked_dir / "store.duckdb", data_dir=locked_dir, static_dir=None)
    client = TestClient(create_app(settings))
    for path in ("/api/health", "/api/catalog"):
        r = client.get(path)
        assert r.status_code == 503, path
        assert "cannot open the data store" in r.json()["detail"]


def test_store_survives_a_killed_first_start(tmp_path):
    """A first start killed before shutdown must leave a store that opens (no WAL replay)."""
    import subprocess
    import sys

    db = tmp_path / "store.duckdb"
    code = (
        "import os, sys; from precinctmap.io.db import get_connection;"
        " get_connection(sys.argv[1]); os._exit(0)"
    )
    subprocess.run([sys.executable, "-c", code, str(db)], check=True)
    assert not (tmp_path / "store.duckdb.wal").exists()
    reopened = subprocess.run(
        [sys.executable, "-c", "import duckdb, sys; duckdb.connect(sys.argv[1]).close()", str(db)],
        capture_output=True,
        text=True,
    )
    assert reopened.returncode == 0, reopened.stderr[-300:]
