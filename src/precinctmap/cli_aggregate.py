"""`precinctmap aggregate`: materialize results by geography and report reconciliation."""

from typing import Annotated

import typer

from precinctmap.aggregate.reconcile import ReconcileSummary
from precinctmap.aggregate.run import aggregate, election_ids
from precinctmap.aggregate.villages import village_checks
from precinctmap.config import load_settings
from precinctmap.io.db import get_connection

aggregate_app = typer.Typer(no_args_is_help=True, help="Results by geography.")

ElectionOpt = Annotated[str | None, typer.Option("--election", help="One election id.")]


def echo_summaries(summaries: list[ReconcileSummary]) -> None:
    for s in summaries:
        typer.echo(
            f"{s.election_id}  {s.geography:<16} {s.choices:>4} choices  reconciled"
            f" {s.choices - s.failures}/{s.choices}  source {s.source:,.0f} = mapped"
            f" {s.mapped:,.2f} + excluded {s.excluded:,.0f} + unassigned {s.unassigned:,.0f}"
        )


@aggregate_app.command("run")
def run(election: ElectionOpt = None) -> None:
    """Rebuild geo_results for every election (or one) and assert totals reconcile."""
    con = get_connection(load_settings().db_path)
    echo_summaries(aggregate(con, [election] if election else None))


@aggregate_app.command("report")
def report(election: ElectionOpt = None) -> None:
    """Reconciliation status and the village allocation check."""
    con = get_connection(load_settings().db_path)
    for e in [election] if election else election_ids(con):
        rows = con.execute(
            "SELECT geography, count(*), count(*) FILTER (WHERE NOT ok) FROM geo_reconciliation"
            " WHERE election_id = ? GROUP BY 1 ORDER BY 1",
            [e],
        ).fetchall()
        status = ", ".join(f"{g} {n - bad}/{n}" for g, n, bad in rows) or "not aggregated"
        typer.echo(f"{e}: reconciled {status}")
        for v in village_checks(con, e):
            share = f"{v.ballot_share:.1%}" if v.ballot_share is not None else "no usable contest"
            typer.echo(
                f"    {v.village:<13} in {v.host_precinct:<11} population share"
                f" {v.population_share:.1%}  ballot share {share}"
            )
