"""CLI: `precinctmap serve`, the API (and built client) on PRECINCTMAP_HOST:PRECINCTMAP_PORT."""

from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from dotenv import load_dotenv

from precinctmap.config import load_settings


def serve(
    reload: Annotated[bool, typer.Option("--reload", help="Restart on code changes.")] = False,
) -> None:
    """Run the API. Settings come from the environment, then `.env` (never overriding)."""
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file, override=False)
    settings = load_settings()
    typer.echo(f"serving on http://{settings.host}:{settings.port}")
    # app_dir: the `app` package lives at the repo root, which a console script doesn't put on
    # sys.path (the `uvicorn` command adds the working directory itself).
    uvicorn.run(
        "app.api.main:app", host=settings.host, port=settings.port, reload=reload, app_dir="."
    )
