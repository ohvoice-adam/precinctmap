from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
from precinctmap import __version__
from precinctmap.config import Settings


def _settings(tmp_path: Path, static: Path | None = None) -> Settings:
    return Settings(db_path=tmp_path / "t.duckdb", data_dir=tmp_path, static_dir=static)


def test_health_reports_ok_and_version(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": __version__}


def test_root_is_404_without_static_dir(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    assert client.get("/").status_code == 404


def test_serves_built_client_when_static_dir_exists(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<title>precinctmap</title>")
    client = TestClient(create_app(_settings(tmp_path, web)))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<title>precinctmap</title>" in resp.text
    assert client.get("/api/health").json()["status"] == "ok"
