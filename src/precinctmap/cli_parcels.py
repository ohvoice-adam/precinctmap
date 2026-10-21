"""CLI: `precinctmap addresses load` (voter-file addresses) and
`precinctmap parcels review|commit|status`."""

from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from precinctmap.config import load_settings
from precinctmap.ingest.errors import StagingError
from precinctmap.io.db import get_connection
from precinctmap.parcels.ingest import commit_parcels, load_addresses, stage_parcels, staging_dir
from precinctmap.parcels.report import render
from precinctmap.parcels.stats import materialize_stats

addresses_app = typer.Typer(no_args_is_help=True, help="De-identified address -> precinct table.")
parcels_app = typer.Typer(no_args_is_help=True, help="Auditor parcels located in precincts.")

FileArg = Annotated[Path, typer.Argument(exists=True, dir_okay=False)]
AsOf = Annotated[str, typer.Option("--as-of", help="Date the file describes, YYYY-MM-DD.")]


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{value!r} is not YYYY-MM-DD", param_hint="--as-of") from exc


@addresses_app.command("load")
def addresses_load(
    path: FileArg,
    as_of: AsOf,
    commit: Annotated[
        bool, typer.Option("--commit", help="Replace the active address table.")
    ] = False,
    reprocess: Annotated[
        bool, typer.Option("--reprocess", help="Reload the same file (after code changes).")
    ] = False,
) -> None:
    """Reduce the county voter file to street addresses with precinct and council district.

    Only address, precinct, city, and council columns are read; no personal data is kept.
    Without --commit this only reports what would be loaded.
    """
    con = get_connection(load_settings().db_path)
    r = load_addresses(con, path, _date(as_of), commit, reprocess)
    typer.echo(
        f"{r.action}: {r.addresses:,} addresses from {r.rows_read:,} rows"
        f" ({r.split_addresses} split across precincts, {r.columbus_addresses:,} with a"
        f" Columbus council district)"
        + ("" if commit or r.action == "noop" else "; add --commit to load")
    )


@parcels_app.command("review")
def parcels_review(
    path: FileArg,
    as_of: AsOf,
    reprocess: Annotated[
        bool, typer.Option("--reprocess", help="Re-derive the active file (after code changes).")
    ] = False,
) -> None:
    """Locate every parcel and print the review report. Nothing is committed."""
    settings = load_settings()
    con = get_connection(settings.db_path)
    report = stage_parcels(con, settings, path, _date(as_of), reprocess)
    typer.echo(render(report))
    if report["status"] != "noop":
        typer.echo(f"  full report: {staging_dir(settings, report['staging_id']) / 'report.txt'}")


@parcels_app.command("commit")
def parcels_commit(
    staging_id: str,
    replace: Annotated[
        bool, typer.Option("--replace", help="Allow replacing the active parcel file.")
    ] = False,
) -> None:
    """Commit a reviewed parcel batch."""
    settings = load_settings()
    detail = commit_parcels(get_connection(settings.db_path), settings, staging_id, replace)
    typer.echo(f"committed {staging_id}: {detail}")


@parcels_app.command("stats")
def parcels_stats() -> None:
    """Rebuild the area statistics of the active parcel file (after a measure is added or
    changed). Parcel locations are kept; nothing is re-read from the auditor file."""
    con = get_connection(load_settings().db_path)
    row = con.execute(
        "SELECT file_id, filename FROM parcel_files WHERE status = 'active'"
    ).fetchone()
    if row is None:
        raise StagingError("no parcel file is loaded; run `parcels review` and `parcels commit`")
    typer.echo(f"{row[1]}: {materialize_stats(con, row[0]):,} area statistics rebuilt")


@parcels_app.command("status")
def parcels_status() -> None:
    """Active parcel and address files with coverage by method."""
    con = get_connection(load_settings().db_path)
    for row in con.execute(
        "SELECT f.filename, f.as_of, f.parcels, a.filename, a.as_of FROM parcel_files f"
        " LEFT JOIN address_files a ON a.file_id = f.address_file_id WHERE f.status = 'active'"
    ).fetchall():
        typer.echo(
            f"parcels {row[0]} as of {row[1]}: {row[2]:,};"
            f" address cross-check {row[3]} as of {row[4]}"
        )
    for geo, rows in (
        (
            "precinct",
            "SELECT precinct_method, count(*) FROM parcel_assignments GROUP BY 1 ORDER BY 2 DESC",
        ),
        (
            "council",
            "SELECT council_method, count(*) FROM parcel_assignments GROUP BY 1 ORDER BY 2 DESC",
        ),
    ):
        typer.echo(f"  {geo}: " + ", ".join(f"{m} {n:,}" for m, n in con.execute(rows).fetchall()))
