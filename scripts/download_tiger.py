#!/usr/bin/env python3
"""Download the Census TIGER/Line files that config/boundaries.toml points at.

Files land at the paths the config expects (relative to the data dir, default `data/`), so
`precinctmap boundaries load` works afterwards. Existing files are kept (size checked against
the server) unless --force. Downloads go to `<name>.part` and are renamed only when complete
and a valid zip, so an interrupted run never leaves a half file that looks finished.

Not downloaded (not TIGER; supply them yourself): the BOE precinct shapefile
(boundaries/franklin_precincts_2026/) and Columbus_City_Council_Districts.geojson.

Usage:
  uv run python scripts/download_tiger.py              # fetch whatever is missing
  uv run python scripts/download_tiger.py --check      # HEAD requests only: list status/sizes
  uv run python scripts/download_tiger.py --only sld   # name filter (substring, repeatable)
  uv run python scripts/download_tiger.py --force      # re-download even if present
"""

import argparse
import hashlib
import logging
import os
import sys
import tomllib
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

BASE = "https://www2.census.gov/geo/tiger"
USER_AGENT = "precinctmap data setup (open source)"
CHUNK = 1 << 20
log = logging.getLogger("download_tiger")


@dataclass(frozen=True)
class TigerFile:
    dest: str  # path relative to the data dir, as written in config/boundaries.toml
    url: str
    why: str

    @property
    def name(self) -> str:
        return Path(self.dest).name


def _f(
    folder: str, name: str, year: int, why: str, subdir: str = "boundaries/tiger_dl"
) -> TigerFile:
    return TigerFile(f"{subdir}/{name}.zip", f"{BASE}/TIGER{year}/{folder}/{name}.zip", why)


MANIFEST: tuple[TigerFile, ...] = (
    _f("COUNTY", "tl_2026_us_county", 2026, "county outline (clip mask)"),
    _f("AREAWATER", "tl_2026_39049_areawater", 2026, "area water for land area"),
    _f("COUSUB", "tl_2026_39_cousub", 2026, "county subdivisions (townships)"),
    _f("TABBLOCK20", "tl_2020_39_tabblock20", 2020, "2020 census blocks (allocation weights)"),
    _f("PLACE", "tl_2026_39_place", 2026, "places (carving villages)", "boundaries"),
    _f("ZCTA520", "tl_2026_us_zcta520", 2026, "ZIP code areas (ZCTA)", "boundaries"),
    _f("SLDL", "tl_2020_39_sldl", 2020, "Ohio House districts, 2011 map"),
    _f("SLDU", "tl_2020_39_sldu", 2020, "Ohio Senate districts, 2011 map"),
    _f("SLDL", "tl_2022_39_sldl", 2022, "Ohio House districts, 2022 map"),
    _f("SLDU", "tl_2022_39_sldu", 2022, "Ohio Senate districts, 2022 map"),
    _f("SLDL", "tl_2026_39_sldl", 2026, "Ohio House districts, 2024 map"),
    _f("SLDU", "tl_2026_39_sldu", 2026, "Ohio Senate districts, 2024 map"),
)


def remote_size(url: str) -> int | None:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        length = resp.headers.get("Content-Length")
    return int(length) if length else None


def download(url: str, target: Path, expected: int | None) -> str:
    """Stream `url` to `target` via a .part file; return the sha256. Raises on a bad file."""
    part = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, part.open("wb") as out:
            while block := resp.read(CHUNK):
                out.write(block)
                h.update(block)
        size = part.stat().st_size
        if expected is not None and size != expected:
            raise OSError(f"{target.name}: got {size:,} bytes, server said {expected:,}")
        if not zipfile.is_zipfile(part):
            raise OSError(f"{target.name}: download is not a valid zip")
        part.replace(target)
    except Exception:
        part.unlink(missing_ok=True)
        log.exception("download of %s failed", url)
        raise
    return h.hexdigest()


def status(f: TigerFile, data_dir: Path) -> tuple[str, int | None, int | None]:
    """('ok' | 'missing' | 'wrong size', local size, remote size)."""
    local = data_dir / f.dest
    remote = remote_size(f.url)
    if not local.exists():
        return "missing", None, remote
    size = local.stat().st_size
    return ("ok" if remote is None or size == remote else "wrong size"), size, remote


def unlisted_config_sources(config: Path, listed: set[str]) -> list[str]:
    """Config paths under boundaries/ that this script neither downloads nor expects you to."""
    raw = tomllib.loads(config.read_text(encoding="utf-8"))
    paths: set[str] = set()
    for s in raw.get("sets", []):
        paths.update(str(s[k]) for k in ("source", "places", "county_subdivisions") if k in s)
    for key in ("blocks", "water"):
        if key in raw:
            paths.add(str(raw[key]["source"]))
    return sorted(p for p in paths if Path(p).name.startswith("tl_") and p not in listed)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--data-dir", type=Path, default=Path(os.environ.get("PRECINCTMAP_DATA_DIR", "data"))
    )
    ap.add_argument("--config", type=Path, default=Path("config/boundaries.toml"))
    ap.add_argument("--check", action="store_true", help="HEAD requests only; download nothing")
    ap.add_argument("--force", action="store_true", help="re-download files that are present")
    ap.add_argument(
        "--only", action="append", default=[], help="only files whose name contains this"
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    files = [f for f in MANIFEST if not args.only or any(o in f.name for o in args.only)]
    if not files:
        print(f"no manifest file matches {args.only}")
        return 2
    failures = 0
    for f in files:
        state, _, remote = status(f, args.data_dir)
        size = f"{(remote or 0) / 1e6:,.1f} MB"
        if args.check or (state == "ok" and not args.force):
            print(f"{state:>10}  {f.dest}  ({size}; {f.why})")
            failures += state == "wrong size"
            continue
        print(f"downloading {f.dest} ({size}; {f.why}) ...", flush=True)
        try:
            sha = download(f.url, args.data_dir / f.dest, remote)
        except Exception:
            failures += 1
            continue
        print(f"{'done':>10}  {f.dest}  sha256 {sha[:16]}")
    missing = unlisted_config_sources(args.config, {f.dest for f in MANIFEST})
    if missing:
        print(f"\nconfig lists TIGER-named files this script does not fetch: {missing}")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        log.exception("download_tiger failed")
        sys.exit(1)
