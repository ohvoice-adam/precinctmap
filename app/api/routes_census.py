"""Census demographics endpoints (public; ACS estimates by area, no individual data)."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from app.api.deps import Db
from app.api.models import MeasureDetail, MeasureStats
from precinctmap.serve.census import census_detail, census_export_csv, census_stats

router = APIRouter(prefix="/api/census")

Geography = Annotated[str, Query(description="precinct | council_district | municipality | zcta")]


@router.get("", response_model=MeasureStats)
def get_census(
    db: Db,
    metric: Annotated[str, Query(description="Metric id from /api/catalog")],
    geography: Geography,
) -> dict[str, Any]:
    return census_stats(db, metric, geography)


@router.get("/detail", response_model=MeasureDetail)
def get_census_detail(
    db: Db, geography: Geography, feature: Annotated[str, Query(description="feature_id")]
) -> dict[str, Any]:
    return census_detail(db, geography, feature)


@router.get("/export.csv")
def get_census_export(db: Db, geography: Geography) -> Response:
    return Response(
        census_export_csv(db, geography),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="census_{geography}.csv"'},
    )
