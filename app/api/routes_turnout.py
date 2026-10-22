"""Turnout endpoints: registered voters, ballots cast and party ballots by area (public)."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from app.api.deps import Db
from app.api.models import Results, TurnoutDetail
from precinctmap.serve.turnout import turnout_results
from precinctmap.serve.turnout_detail import turnout_detail, turnout_export_csv

router = APIRouter(prefix="/api/turnout")

Election = Annotated[str, Query(description="election_id from /api/catalog")]
Geography = Annotated[str, Query(description="precinct | council_district | municipality | zcta")]


@router.get("", response_model=Results)
def get_turnout(db: Db, election: Election, geography: Geography) -> dict[str, Any]:
    """Same shape as /api/results: `v` holds ballots per party, in `choices` order."""
    return turnout_results(db, election, geography)


@router.get("/detail", response_model=TurnoutDetail)
def get_turnout_detail(
    db: Db, election: Election, geography: Geography, feature: Annotated[str, Query()]
) -> dict[str, Any]:
    return turnout_detail(db, election, geography, feature)


@router.get("/export.csv")
def get_turnout_export(db: Db, election: Election, geography: Geography) -> Response:
    return Response(
        turnout_export_csv(db, election, geography),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{election}_turnout_{geography}.csv"'
        },
    )
