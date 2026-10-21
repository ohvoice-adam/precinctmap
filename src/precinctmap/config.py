"""Runtime settings read from environment variables (see `.env.example`)."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Paths the library, CLI, and API share.

    `static_dir` is the built web client; None in development, where Vite serves it.
    """

    db_path: Path
    data_dir: Path
    static_dir: Path | None
    county: str = "Franklin"


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build settings from `env` (defaults to `os.environ`), applying repo defaults."""
    source = os.environ if env is None else env
    data_dir = Path(source.get("PRECINCTMAP_DATA_DIR", "data"))
    static = source.get("PRECINCTMAP_STATIC_DIR")
    return Settings(
        db_path=Path(source.get("PRECINCTMAP_DB_PATH", str(data_dir / "precinctmap.duckdb"))),
        data_dir=data_dir,
        static_dir=Path(static) if static else None,
        county=source.get("PRECINCTMAP_COUNTY", "Franklin"),
    )
