"""CLI commands that change the store: `ingest` (review / commit) and `boundaries`."""

import logging
from datetime import date
from pathlib import Path
from typing import Annotated

import duckdb
import typer

from precinctmap.aggregate.run import aggregate
from precinctmap.catalog.calendar import ElectionType
from precinctmap.cli_aggregate import echo_summaries
from precinctmap.config import Settings, load_settings
from precinctmap.ingest.commit import commit_staging
from precinctmap.ingest.errors import IngestError
from precinctmap.ingest.report_text import render
from precinctmap.ingest.staging import stage_file
from precinctmap.io.db import get_connection

log = logging.getLogger("precinctmap")

_TYPES: dict[str, ElectionType] = {"primary": "primary", "general": "general", "special": "special"}


def _parse_date(value: str | None, option: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{value!r} is not YYYY-MM-DD", param_hint=option) from exc


def ingest(
    files: Annotated[
        list[Path] | None, typer.Argument(help="Results files to stage for review.")
    ] = None,
    review: bool = typer.Option(False, "--review", help="Stage files and print review reports."),
    commit: str | None = typer.Option(None, "--commit", help="Commit a reviewed staging id."),
    election_date: str | None = typer.Option(None, help="YYYY-MM-DD when the file name lacks it."),
    election_type: str | None = typer.Option(None, help="primary | general | special"),
    full: bool = typer.Option(False, "--full", help="List every contest in the printed report."),
    certified: bool | None = typer.Option(
        None, "--certified/--not-certified", help="Override the certified flag."
    ),
    reprocess: bool = typer.Option(
        False, "--reprocess", help="Re-derive an already-ingested file (after corrections)."
    ),
    replace: bool = typer.Option(
        False, "--replace", help="With --commit: allow replacing the election's loaded file."
    ),
) -> None:
    """Stage files for review (--review) or commit a reviewed batch (--commit ID)."""
    if bool(review) == bool(commit):
        raise typer.BadParameter("use exactly one of --review FILES... or --commit STAGING_ID")
    settings = load_settings()
    con = get_connection(settings.db_path)
    if commit:
        result = commit_staging(con, settings, commit, allow_replace=replace)
        typer.echo(f"{result.action}: {result.election_id} ({result.detail})")
        if result.action == "commit":
            echo_summaries(aggregate(con, [result.election_id]))
        return
    if not files:
        raise typer.BadParameter("--review needs at least one file")
    if election_type is not None and election_type not in _TYPES:
        raise typer.BadParameter(f"{election_type!r}", param_hint="--election-type")
    override_type = _TYPES[election_type] if election_type else None
    override_date = _parse_date(election_date, "--election-date")
    overrides = (override_date, override_type, certified, reprocess)
    if _review(con, settings, files, overrides, full):
        raise typer.Exit(code=1)


def _review(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    files: list[Path],
    overrides: tuple[date | None, ElectionType | None, bool | None, bool],
    full: bool,
) -> int:
    """Stage and print each file; returns how many failed."""
    failed = 0
    for path in files:
        try:
            staged = stage_file(con, settings, path, *overrides)
        except IngestError as exc:
            failed += 1
            log.error("%s: %s", path.name, exc)
            typer.echo(f"FAILED {path.name}: {exc}\n", err=True)
            continue
        typer.echo(render(staged.report, None if full else 15))
        typer.echo(f"  full report: {staged.directory / 'report.txt'}\n")
    return failed
