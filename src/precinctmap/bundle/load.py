"""Load a data bundle into an empty store (see bundle/export.py for the layout).

Fails loudly on anything unexpected: another format, a newer schema than this software,
any file whose sha256 differs from the manifest, a row count that differs after loading, or
a store that already holds data. Results by geography are rebuilt and re-reconciled.
"""

import json
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from precinctmap.aggregate.run import aggregate
from precinctmap.bundle.export import FORMAT, FORMAT_VERSION, BundleError, sha256
from precinctmap.config import Settings


@dataclass
class LoadSummary:
    tables: int
    rows: int
    sources: int
    elections_reconciled: int
    vintage: list[dict[str, Any]]


def _extract(archive: Path, work: Path) -> Path:
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(work, filter="data")  # refuses absolute paths, '..' and links out
    root = work / FORMAT
    if not (root / "manifest.json").exists():
        raise BundleError(f"{archive.name}: no {FORMAT}/manifest.json inside")
    return root


def _check(con: duckdb.DuckDBPyConnection, root: Path) -> dict[str, Any]:
    m: dict[str, Any] = json.loads((root / "manifest.json").read_text())
    if m.get("format") != FORMAT or m.get("format_version") != FORMAT_VERSION:
        raise BundleError(
            f"not a {FORMAT} v{FORMAT_VERSION} bundle: {m.get('format')} v{m.get('format_version')}"
        )
    ours = con.execute("SELECT max(version) FROM schema_migrations").fetchone()
    if m["schema_version"] > (ours[0] if ours else 0):
        raise BundleError(
            f"bundle schema {m['schema_version']} is newer than this software's; update precinctmap"
        )
    files = [(t["file"], t["sha256"]) for t in m["tables"].values()] + [
        (s["path"], s["sha256"]) for s in m["sources"]
    ]
    bad = [f for f, want in files if not (root / f).exists() or sha256(root / f) != want]
    if bad:
        raise BundleError(f"{len(bad)} files don't match the manifest's sha256: {bad[:3]}")
    return m


def _require_empty(con: duckdb.DuckDBPyConnection, tables: list[str]) -> None:
    filled = [t for t in tables if con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]]  # type: ignore[index]
    if filled:
        raise BundleError(
            f"the store already has data in {filled[:4]}; load bundles into an empty store"
            " (move data/precinctmap.duckdb aside first)"
        )


def _insert(con: duckdb.DuckDBPyConnection, root: Path, tables: dict[str, Any]) -> int:
    con.execute("BEGIN")
    try:
        for name, t in tables.items():
            path = (root / t["file"]).as_posix().replace("'", "''")
            con.execute(f"INSERT INTO {name} BY NAME SELECT * FROM read_parquet('{path}')")
            got = con.execute(f"SELECT count(*) FROM {name}").fetchone()
            if not got or got[0] != t["rows"]:
                raise BundleError(f"{name}: {got} rows loaded, manifest says {t['rows']}")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return sum(t["rows"] for t in tables.values())


def _place_sources(
    con: duckdb.DuckDBPyConnection, settings: Settings, root: Path, sources: list[dict[str, Any]]
) -> None:
    """Results spreadsheets go to data/raw/ (stored_path updated); ACS files to raw/census/."""
    raw = settings.data_dir / "raw"
    for s in sources:
        rel = Path(s["path"])
        dest = (
            raw / rel.name
            if s["kind"] == "results"
            else raw / "census" / rel.parent.name / rel.name
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dest)
        if s["kind"] == "results":
            con.execute(
                "UPDATE source_files SET stored_path = ? WHERE sha256 = ?", [str(dest), s["sha256"]]
            )


def load_bundle(con: duckdb.DuckDBPyConnection, settings: Settings, archive: Path) -> LoadSummary:
    work = settings.data_dir / ".bundle-load"
    try:
        root = _extract(archive, work)
        m = _check(con, root)
        _require_empty(con, list(m["tables"]))
        rows = _insert(con, root, m["tables"])
        _place_sources(con, settings, root, m["sources"])
        summaries = aggregate(con)  # rebuilds geo_* and raises if any total fails to reconcile
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return LoadSummary(
        len(m["tables"]),
        rows,
        len(m["sources"]),
        len({s.election_id for s in summaries}),
        m["datasets"],
    )
