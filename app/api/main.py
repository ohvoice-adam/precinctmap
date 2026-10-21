"""FastAPI app: read endpoints, admin ingest, and (in Docker) the built web client."""

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.api import routes_admin, routes_census, routes_property, routes_read
from app.api.auth import require_admin
from precinctmap import __version__
from precinctmap.aggregate.reconcile import ReconciliationError
from precinctmap.config import Settings, load_settings
from precinctmap.ingest.errors import IngestError
from precinctmap.io.db import StoreLockedError, StoreUnavailableError, get_connection
from precinctmap.registry.store import BoundaryError
from precinctmap.serve.geo import GeoNotFoundError
from precinctmap.serve.results import NotFoundError

log = logging.getLogger("precinctmap.api")


class Health(BaseModel):
    status: str
    version: str


def _error(status: int) -> object:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        if status >= 500:
            log.error("%s %s failed: %s", request.method, request.url.path, exc, exc_info=exc)
        return JSONResponse({"detail": str(exc)}, status_code=status)

    return handler


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API. Serves the built web client at `/` when `settings.static_dir` exists."""
    settings = settings or load_settings()
    api = FastAPI(
        title="precinctmap",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    api.state.settings = settings
    api.add_middleware(GZipMiddleware, minimum_size=1024)  # GeoJSON compresses ~5x
    for exc, status in (
        (NotFoundError, 404),
        (GeoNotFoundError, 404),
        (IngestError, 422),
        (BoundaryError, 422),
        (ReconciliationError, 500),
        (StoreUnavailableError, 503),  # e.g. ./data not writable: say so instead of a bare 500
        (StoreLockedError, 503),
    ):
        api.add_exception_handler(exc, _error(status))  # type: ignore[arg-type]

    @api.get("/api/health")
    def health() -> Health:
        """Ok only when the store opens, so Docker's healthcheck catches an unusable ./data."""
        get_connection(settings.db_path)
        return Health(status="ok", version=__version__)

    api.include_router(routes_read.router)
    api.include_router(routes_property.router)
    api.include_router(routes_census.router)
    api.include_router(routes_admin.router)
    if settings.static_dir is not None:
        admin_page = settings.static_dir / "admin.html"

        # Registered before the static mount, so /admin.html never bypasses the login.
        @api.get("/admin", include_in_schema=False, dependencies=[Depends(require_admin)])
        @api.get("/admin.html", include_in_schema=False, dependencies=[Depends(require_admin)])
        def admin() -> FileResponse:
            return FileResponse(admin_page, headers={"Cache-Control": "no-store"})

        if settings.static_dir.is_dir():
            api.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="web")
        else:
            log.error(
                "PRECINCTMAP_STATIC_DIR=%s is not a directory; web client not served",
                settings.static_dir,
            )
    return api


app = create_app()
