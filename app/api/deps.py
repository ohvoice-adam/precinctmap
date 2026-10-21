"""Request-scoped dependencies. Each request gets its own cursor on the shared connection
(a DuckDB connection is not safe to share across threads; cursors are)."""

from collections.abc import Iterator
from typing import Annotated

import duckdb
from fastapi import Depends, Request

from precinctmap.config import Settings
from precinctmap.io.db import get_connection


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_db(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[duckdb.DuckDBPyConnection]:
    cursor = get_connection(settings.db_path).cursor()
    try:
        yield cursor
    finally:
        cursor.close()


Db = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
