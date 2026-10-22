"""Write a data bundle from the store: `precinctmap-data.tar.gz` plus its .sha256.

Layout inside the archive (one top-level folder, `precinctmap-data/`):
  manifest.json     format/schema versions, every file with rows and sha256, dataset vintages
  DATA.md           the same, for people: vintage, publisher, where to get updates, terms
  tables/*.parquet  every table except the ones rebuilt on load (zstd; geometry as GeoParquet,
                    coordinates are the store's EPSG:4269 lon/lat)
  sources/results/  the election spreadsheets exactly as ingested (sha256 = file_id)
  sources/census/   the county rows of each ACS table, as fetched
"""

import hashlib
import json
import shutil
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from precinctmap import __version__
from precinctmap.bundle.notes import render_notes
from precinctmap.bundle.sources import DATASETS, vintages
from precinctmap.config import Settings

FORMAT = "precinctmap-data"
FORMAT_VERSION = 1
ARCHIVE = "precinctmap-data.tar.gz"
# Rebuilt on load by `aggregate`, which also re-asserts every reconciliation.
REBUILT = ("geo_results", "geo_contributions", "geo_turnout", "geo_reconciliation")
SKIPPED = ("schema_migrations", *REBUILT)


class BundleError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute("SELECT table_name FROM information_schema.tables ORDER BY 1").fetchall()
    return [t for (t,) in rows if t not in SKIPPED]


def _export_tables(con: duckdb.DuckDBPyConnection, root: Path) -> dict[str, dict[str, Any]]:
    (root / "tables").mkdir(parents=True)
    out = {}
    for t in _tables(con):
        rel = f"tables/{t}.parquet"
        path = (root / rel).as_posix().replace("'", "''")
        con.execute(f"COPY (SELECT * FROM {t}) TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
        rows = con.execute(f"SELECT count(*) FROM {t}").fetchone()
        out[t] = {"file": rel, "rows": int(rows[0]) if rows else 0, "sha256": sha256(root / rel)}
    return out


def _copy_sources(
    con: duckdb.DuckDBPyConnection, settings: Settings, root: Path
) -> list[dict[str, Any]]:
    """Results spreadsheets (checked against their recorded sha256) and fetched ACS files."""
    out = []
    for fname, sha, stored in con.execute(
        "SELECT filename, sha256, stored_path FROM source_files WHERE status = 'active' ORDER BY 1"
    ).fetchall():
        src = _stored(Path(stored), settings)
        if not src.exists() or sha256(src) != sha:
            raise BundleError(
                f"{fname}: {src} is missing or no longer matches its sha256 {sha[:12]}"
            )
        out.append(_copy(src, root, f"sources/results/{sha[:12]}__{fname}", "results"))
    for release, fname, sha in con.execute(
        "SELECT release_id, filename, sha256 FROM census_files ORDER BY 1, 2"
    ).fetchall():
        src = settings.data_dir / "raw" / "census" / release / fname
        if not src.exists() or sha256(src) != sha:
            raise BundleError(
                f"{fname}: {src} is missing or no longer matches its sha256 {sha[:12]}"
            )
        out.append(_copy(src, root, f"sources/census/{release}/{fname}", "census"))
    return out


def _stored(path: Path, settings: Settings) -> Path:
    """A stored copy as recorded, or by name under this data folder: files ingested through the
    admin page record the container's path (/app/data/raw/...)."""
    return path if path.exists() else settings.data_dir / "raw" / path.name


def _copy(src: Path, root: Path, rel: str, kind: str) -> dict[str, Any]:
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return {"path": rel, "kind": kind, "sha256": sha256(dest)}


def export_bundle(con: duckdb.DuckDBPyConnection, settings: Settings, out_dir: Path) -> Path:
    """Write the archive into `out_dir`; returns its path. Refuses an empty store."""
    if not con.execute("SELECT count(*) FROM boundary_sets").fetchone()[0]:  # type: ignore[index]
        raise BundleError("the store has no boundaries loaded; nothing to bundle")
    out_dir.mkdir(parents=True, exist_ok=True)
    staging = out_dir / FORMAT
    if staging.exists():
        shutil.rmtree(staging)
    tables = _export_tables(con, staging)
    sources = _copy_sources(con, settings, staging)
    schema = con.execute("SELECT max(version) FROM schema_migrations").fetchone()
    lines = vintages(con)
    manifest = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "precinctmap_version": __version__,
        "schema_version": int(schema[0]) if schema else 0,
        "county": settings.county,
        "rebuilt_on_load": list(REBUILT),
        "tables": tables,
        "sources": sources,
        "datasets": [{"key": d.key, "title": d.title, "vintage": lines[d.key]} for d in DATASETS],
    }
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (staging / "DATA.md").write_text(render_notes(manifest, lines))
    archive = out_dir / ARCHIVE
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(staging, arcname=FORMAT)
    (out_dir / f"{ARCHIVE}.sha256").write_text(f"{sha256(archive)}  {ARCHIVE}\n")
    shutil.copy2(staging / "DATA.md", out_dir / "DATA.md")
    shutil.rmtree(staging)
    return archive
