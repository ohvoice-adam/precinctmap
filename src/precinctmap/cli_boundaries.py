"""`precinctmap boundaries`: load the registry, build crosswalks, report coverage per election."""

from pathlib import Path
from typing import Annotated

import duckdb
import typer

from precinctmap.aggregate.run import aggregate
from precinctmap.cli_aggregate import echo_summaries
from precinctmap.config import load_settings
from precinctmap.io.db import get_connection
from precinctmap.registry.blocks import load_blocks
from precinctmap.registry.config import DEFAULT_CONFIG, RegistryConfig, load_config
from precinctmap.registry.crosswalk_build import build_crosswalks, crosswalk_pairs
from precinctmap.registry.loader import load_registry
from precinctmap.registry.report import coverage

boundaries_app = typer.Typer(no_args_is_help=True, help="Boundary registry and crosswalks.")


def _blocks_loaded(con: duckdb.DuckDBPyConnection, cfg: RegistryConfig) -> bool:
    row = con.execute(
        "SELECT count(*) FROM census_blocks WHERE county = ? AND vintage = ?",
        [cfg.county, cfg.blocks.vintage],
    ).fetchone()
    return bool(row and row[0])


def _missing_pairs(con: duckdb.DuckDBPyConnection, cfg: RegistryConfig) -> bool:
    built = {
        (p, t)
        for p, t in con.execute(
            "SELECT DISTINCT precinct_set_id, target_set_id FROM precinct_crosswalk"
        ).fetchall()
    }
    return any((p, t) not in built for p, t, _ in crosswalk_pairs(con, cfg.county))


@boundaries_app.command("load")
def load(
    config: Annotated[Path, typer.Option(help="Registry file.")] = DEFAULT_CONFIG,
    replace: Annotated[
        list[str] | None, typer.Option("--replace", help="Reload a changed set (repeatable).")
    ] = None,
    reload_blocks: bool = typer.Option(False, help="Reload census blocks."),
) -> None:
    """Make the store match the registry file, then (re)build crosswalks as needed."""
    settings = load_settings()
    con = get_connection(settings.db_path)
    cfg = load_config(config)
    changed = False
    if reload_blocks or not _blocks_loaded(con, cfg):
        n = load_blocks(con, cfg.blocks, settings.data_dir, cfg.county)
        typer.echo(f"blocks: loaded {n:,} ({cfg.blocks.vintage})")
        changed = True
    for r in load_registry(con, cfg, settings.data_dir, set(replace or [])):
        typer.echo(
            f"{r.set_id}: {r.action}"
            + (f" ({r.features} features, {r.repairs} repairs)" if r.features else "")
        )
        changed = changed or r.action != "unchanged"
    if changed or _missing_pairs(con, cfg):
        for s in build_crosswalks(con, cfg):
            typer.echo(
                f"crosswalk {s.precinct_set_id} -> {s.target_set_id}: eligible {s.eligible},"
                f" exact {s.exact}, allocated {s.allocated}, excluded {s.excluded},"
                f" no overlap {s.no_overlap}, log entries {len(s.log)}"
            )
        echo_summaries(aggregate(con))  # crosswalks changed: rebuild results by geography
    else:
        typer.echo("crosswalks up to date")


@boundaries_app.command("list")
def list_sets() -> None:
    """List loaded boundary sets with validity windows and repair counts."""
    con = get_connection(load_settings().db_path)
    rows = con.execute(
        "SELECT b.boundary_set_id, b.geography, b.valid_from, b.valid_to, b.native_from,"
        " (SELECT count(*) FROM features f WHERE f.boundary_set_id = b.boundary_set_id),"
        " (SELECT count(*) FROM geometry_repairs g WHERE g.boundary_set_id = b.boundary_set_id)"
        " FROM boundary_sets b ORDER BY b.geography, b.valid_from"
    ).fetchall()
    for set_id, geo, vf, vt, nf, n, rep in rows:
        window = f"{vf} .. {vt or 'open'}" + (f" (native from {nf})" if nf and nf != vf else "")
        typer.echo(f"{geo:<16} {set_id:<38} {window:<44} {n:>4} features {rep:>3} repairs")


@boundaries_app.command("report")
def report() -> None:
    """Per election: precinct match rate and exact / allocated / excluded counts by geography."""
    con = get_connection(load_settings().db_path)
    for e in coverage(con):
        rate = (
            f"{e.matched}/{e.precincts} ({e.matched / e.precincts:.1%})" if e.precincts else "n/a"
        )
        retro = " (retroactive)" if e.retroactive else ""
        typer.echo(f"{e.election_id}: precincts {e.precinct_set_id or 'NONE'}{retro}  match {rate}")
        if e.unmatched:
            typer.echo(f"    unmatched: {', '.join(e.unmatched)}")
        for g in e.geographies:
            if g.target_set_id is None:
                typer.echo(f"    {g.geography:<16} no boundary set covers this date")
                continue
            typer.echo(
                f"    {g.geography:<16} {g.target_set_id:<38} exact {g.exact:>4}  allocated"
                f" {g.allocated:>4}  excluded {g.excluded:>4}  no overlap {g.no_overlap}"
                f"  missing {len(g.missing)}"
            )
