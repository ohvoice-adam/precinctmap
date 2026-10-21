"""CLI: `precinctmap census fetch|load|status` (ACS 5-year demographics)."""

from datetime import date
from typing import Annotated

import typer

from precinctmap.census.load import (
    commit_release,
    county_fips,
    fetch_release,
    release_dir,
    review_release,
)
from precinctmap.census.report import render
from precinctmap.config import load_settings
from precinctmap.io.db import get_connection
from precinctmap.registry.config import DEFAULT_CONFIG, load_config

census_app = typer.Typer(no_args_is_help=True, help="ACS 5-year census demographics.")

Year = Annotated[int, typer.Option("--year", help="Last year of the 5-year release, e.g. 2024.")]
AsOf = Annotated[str, typer.Option("--as-of", help="Use boundary sets valid on this date.")]


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{value!r} is not YYYY-MM-DD", param_hint="--as-of") from exc


@census_app.command("fetch")
def census_fetch(year: Year, as_of: AsOf) -> None:
    """Download each ACS table (no API key) and keep only this county's rows."""
    settings = load_settings()
    con = get_connection(settings.db_path)
    fips = county_fips(con, settings.county, _date(as_of))
    for f in fetch_release(settings.data_dir, year, fips):
        unit = f"{f.block_groups} block groups" if f.block_groups else f"{f.tracts} tracts"
        typer.echo(f"{f.table}: {unit}, sha256 {f.sha256[:12]}")
    typer.echo(f"saved under {release_dir(settings.data_dir, year)}")


@census_app.command("load")
def census_load(
    year: Year,
    as_of: AsOf,
    commit: Annotated[bool, typer.Option("--commit", help="Write the release.")] = False,
) -> None:
    """Allocate the fetched tables to every geography; review, then --commit."""
    settings = load_settings()
    con = get_connection(settings.db_path)
    cfg = load_config(DEFAULT_CONFIG)
    review = review_release(con, cfg, settings.data_dir, year, _date(as_of))
    typer.echo(render(review))
    if not commit:
        typer.echo("\nNothing written; add --commit to load this release.")
        return
    action = commit_release(con, review, cfg.county)
    typer.echo(f"\n{action}: {review.release_id}, {len(review.computed.stats):,} statistics")


@census_app.command("status")
def census_status() -> None:
    """Loaded releases."""
    con = get_connection(load_settings().db_path)
    rows = con.execute(
        "SELECT r.release_id, r.label, r.as_of, count(s.metric) FROM census_releases r"
        " LEFT JOIN census_stats s USING (release_id) GROUP BY ALL ORDER BY 1"
    ).fetchall()
    if not rows:
        typer.echo("No census release loaded.")
    for rid, label, as_of, n in rows:
        typer.echo(f"{rid}: {label}, boundaries as of {as_of}, {n:,} statistics")
