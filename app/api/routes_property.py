"""Residential property statistics endpoints (public; no PII is ever returned)."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from app.api.deps import Db
from app.api.models import MeasureDetail, MeasureStats
from precinctmap.serve.property import property_detail, property_export_csv, property_stats

router = APIRouter(prefix="/api/property")

Geography = Annotated[str, Query(description="precinct | council_district | municipality | zcta")]


@router.get("", response_model=MeasureStats)
def get_property(
    db: Db,
    metric: Annotated[str, Query(description="Metric id from /api/catalog")],
    geography: Geography,
) -> dict[str, Any]:
    return property_stats(db, metric, geography)


@router.get("/detail", response_model=MeasureDetail)
def get_property_detail(
    db: Db, geography: Geography, feature: Annotated[str, Query(description="feature_id")]
) -> dict[str, Any]:
    return property_detail(db, geography, feature)


@router.get("/export.csv")
def get_property_export(db: Db, geography: Geography) -> Response:
    return Response(
        property_export_csv(db, geography),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="residential-property_{geography}.csv"'
        },
    )
