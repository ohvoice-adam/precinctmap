"""CLI: `precinctmap bundle export|load|info` (data bundles; see bundle/export.py)."""

import json
import tarfile
from pathlib import Path
from typing import Annotated

import typer

from precinctmap.bundle.export import ARCHIVE, FORMAT, export_bundle
from precinctmap.bundle.load import load_bundle
from precinctmap.config import load_settings
from precinctmap.io.db import get_connection

bundle_app = typer.Typer(no_args_is_help=True, help="Package or load the normalized data.")

Archive = Annotated[Path, typer.Argument(exists=True, dir_okay=False, help=f"A {ARCHIVE} file.")]


@bundle_app.command("export")
def bundle_export(
    out: Annotated[Path, typer.Option("--out", help="Folder for the archive.")] = Path("dist"),
) -> None:
    """Write every loaded table, the source spreadsheets and DATA.md into one archive."""
    settings = load_settings()
    archive = export_bundle(get_connection(settings.db_path), settings, out)
    size = archive.stat().st_size / 1e6
    typer.echo(f"wrote {archive} ({size:.1f} MB), {archive.name}.sha256 and DATA.md in {out}")


@bundle_app.command("load")
def bundle_load(archive: Archive) -> None:
    """Load a bundle into an empty store; checks every sha256 and re-reconciles all totals."""
    settings = load_settings()
    s = load_bundle(get_connection(settings.db_path), settings, archive)
    typer.echo(
        f"loaded {s.tables} tables ({s.rows:,} rows) and {s.sources} source files;"
        f" {s.elections_reconciled} elections rebuilt and reconciled"
    )
    for d in s.vintage:
        typer.echo(f"  {d['title']}: {'; '.join(d['vintage'][:2]) or 'none'}")


@bundle_app.command("info")
def bundle_info(archive: Archive) -> None:
    """Print a bundle's manifest summary without loading it."""
    with tarfile.open(archive, "r:gz") as tar:
        f = tar.extractfile(f"{FORMAT}/manifest.json")
        if f is None:
            raise typer.BadParameter(f"{archive} has no manifest.json")
        m = json.loads(f.read())
    typer.echo(
        f"{m['format']} v{m['format_version']}, built {m['created_at']},"
        f" schema {m['schema_version']}"
    )
    for d in m["datasets"]:
        typer.echo(f"  {d['title']}:")
        for line in d["vintage"] or ["nothing loaded"]:
            typer.echo(f"    {line}")
