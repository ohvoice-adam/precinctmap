"""`precinctmap` command-line entry point."""

import logging
import sys

import typer

from precinctmap import __version__
from precinctmap.catalog.queries import contests_summary, elections_summary
from precinctmap.cli_aggregate import aggregate_app
from precinctmap.cli_boundaries import boundaries_app
from precinctmap.cli_census import census_app
from precinctmap.cli_ingest import ingest
from precinctmap.cli_parcels import addresses_app, parcels_app
from precinctmap.cli_serve import serve
from precinctmap.config import load_settings
from precinctmap.ingest.errors import IngestError
from precinctmap.io.db import StoreLockedError, StoreUnavailableError, close_all, get_connection
from precinctmap.registry.store import BoundaryError

log = logging.getLogger("precinctmap")

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Election results toolkit.")
app.command()(ingest)
app.add_typer(boundaries_app, name="boundaries")
app.add_typer(aggregate_app, name="aggregate")
app.add_typer(addresses_app, name="addresses")
app.add_typer(parcels_app, name="parcels")
app.add_typer(census_app, name="census")
app.command()(serve)


@app.callback()
def _root(verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging.")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.command()
def version() -> None:
    """Print the precinctmap version."""
    typer.echo(__version__)


@app.command()
def info() -> None:
    """Print the resolved settings (paths only; no secrets are read here)."""
    settings = load_settings()
    typer.echo(f"db_path={settings.db_path}")
    typer.echo(f"data_dir={settings.data_dir}")
    typer.echo(f"static_dir={settings.static_dir}")
    typer.echo(f"listen={settings.host}:{settings.port}")


def _fmt(n: object) -> str:
    return f"{n:,}" if isinstance(n, int) else ("-" if n is None else str(n))


@app.command()
def catalog(
    election: str | None = typer.Option(None, "--election", help="List one election's contests."),
) -> None:
    """List elections (or one election's contests) with coverage and precinct match."""
    con = get_connection(load_settings().db_path)
    if election:
        rows = contests_summary(con, election)
        if not rows:
            raise typer.BadParameter(f"no contests for {election!r}", param_hint="--election")
        for r in rows:
            vf = r["vote_for"] if r["vote_for"] is not None else "?"
            typer.echo(
                f"{r['source_ordinal']:>3} {r['party'] or '-':<4} {r['contest_type']:<9} "
                f"vf {vf}  {r['precincts']:>4} pct {_fmt(r['votes']):>9} votes  {r['name_display']}"
            )
        return
    rows = elections_summary(con)
    if not rows:
        typer.echo("catalog is empty")
        return
    for r in rows:
        match = (
            f"{r['matched']}/{r['precincts']} ({r['matched'] / r['precincts']:.1%})"
            if r["precincts"] and r["matched"] is not None
            else "n/a"
        )
        typer.echo(
            f"{r['election_id']}  {r['label']}  certified={'yes' if r['certified'] else 'no'}\n"
            f"    file {r['filename']} [{r['adapter']}]"
            f"{'  superseded: ' + str(r['superseded_files']) if r['superseded_files'] else ''}\n"
            f"    precincts {_fmt(r['precincts'])}  contests {_fmt(r['contests'])}"
            f" (vote-for known {_fmt(r['vote_for_known'])})  registered {_fmt(r['registered'])}"
            f"  ballots {_fmt(r['ballots'])}\n"
            f"    boundaries {r['boundary_set_id'] or 'NONE'}"
            f"{' (retroactive)' if r['retroactive'] else ''}  match {match}"
        )


def main() -> None:
    """Console-script entry: run the CLI, log any unhandled error with context, exit non-zero."""
    try:
        app()
    except SystemExit:
        raise
    except StoreLockedError as exc:
        log.error("%s", exc)
        sys.exit(2)
    except (IngestError, BoundaryError, StoreUnavailableError, FileNotFoundError) as exc:
        # Expected failures (bad input, staging state, missing files): the message says what to
        # do, so no traceback unless --verbose asked for one.
        log.error("%s", exc)
        log.debug("details", exc_info=exc)
        sys.exit(1)
    except Exception:
        log.exception("precinctmap failed: %s", " ".join(sys.argv[1:]))
        sys.exit(1)
    finally:
        close_all()
