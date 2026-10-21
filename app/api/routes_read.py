"""Read endpoints: catalog, geometry, results, detail, export."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Response

from app.api.deps import AppSettings, Db
from app.api.models import Catalog, Detail, Results
from precinctmap.serve.catalog import catalog
from precinctmap.serve.detail import detail
from precinctmap.serve.export import export_csv, export_geojson
from precinctmap.serve.geo import geojson
from precinctmap.serve.results import results

router = APIRouter(prefix="/api")

Election = Annotated[str, Query(description="Election id, e.g. franklin-2024-11-05-general")]
Contest = Annotated[str, Query(description="Contest id from /api/catalog")]
Geography = Annotated[str, Query(description="precinct | council_district | municipality | zcta")]


@router.get("/catalog", response_model=Catalog)
def get_catalog(db: Db) -> dict[str, Any]:
    return catalog(db)


@router.get("/geo/{geography}", responses={200: {"content": {"application/geo+json": {}}}})
def get_geo(
    geography: str,
    db: Db,
    settings: AppSettings,
    on: Annotated[date, Query(alias="date", description="Election date, YYYY-MM-DD")],
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    etag, body = geojson(db, geography, settings.county, on)
    headers = {"ETag": f'"{etag}"', "Cache-Control": "private, max-age=3600"}
    if if_none_match == f'"{etag}"':
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/geo+json", headers=headers)


@router.get("/results", response_model=Results)
def get_results(
    db: Db, election: Election, contest: Contest, geography: Geography
) -> dict[str, Any]:
    return results(db, election, contest, geography)


@router.get("/results/detail", response_model=Detail)
def get_detail(
    db: Db,
    election: Election,
    contest: Contest,
    geography: Geography,
    feature: Annotated[str, Query(description="feature_id from /api/geo")],
) -> dict[str, Any]:
    return detail(db, election, contest, geography, feature)


def _filename(election: str, contest: str, geography: str, ext: str) -> str:
    stem = f"{election}_{contest.rsplit(':', 1)[-1]}_{geography}"
    return f'attachment; filename="{stem}.{ext}"'


@router.get("/export.csv")
def get_export_csv(db: Db, election: Election, contest: Contest, geography: Geography) -> Response:
    return Response(
        export_csv(db, election, contest, geography),
        media_type="text/csv",
        headers={"Content-Disposition": _filename(election, contest, geography, "csv")},
    )


@router.get("/export.geojson")
def get_export_geojson(
    db: Db, election: Election, contest: Contest, geography: Geography
) -> Response:
    return Response(
        export_geojson(db, election, contest, geography),
        media_type="application/geo+json",
        headers={"Content-Disposition": _filename(election, contest, geography, "geojson")},
    )
