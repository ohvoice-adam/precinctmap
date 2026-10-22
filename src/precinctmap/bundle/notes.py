"""DATA.md: the bundle's notes for people (vintage, sources, updates, terms, privacy)."""

from typing import Any

from precinctmap.bundle.sources import DATASETS


def render_notes(manifest: dict[str, Any], vintage: dict[str, list[str]]) -> str:
    rows = sum(t["rows"] for t in manifest["tables"].values())
    lines = [
        "# precinctmap data bundle",
        "",
        f"Built {manifest['created_at']} by precinctmap {manifest['precinctmap_version']}"
        f" (schema {manifest['schema_version']}) for {manifest['county']} County:"
        f" {len(manifest['tables'])} tables, {rows:,} rows,"
        f" {len(manifest['sources'])} source files.",
        "",
        "## Loading it",
        "",
        "Into an empty store, with the app stopped:",
        "",
        "```bash",
        "precinctmap bundle load precinctmap-data.tar.gz",
        "```",
        "",
        "Every file is checked against the sha256 in manifest.json. Results by geography are",
        f"rebuilt on load ({', '.join(manifest['rebuilt_on_load'])}) and every total is",
        "re-reconciled, so a load that finishes is a load that matches the sources.",
        "",
        "Tables are Parquet (zstd). Geometry is GeoParquet; coordinates are longitude/latitude",
        "in EPSG:4269 (NAD83), which the files label CRS84 (they differ by about a meter).",
        "",
    ]
    for d in DATASETS:
        lines += [f"## {d.title}", ""]
        lines += [f"- **In this bundle:** {v}" for v in vintage.get(d.key) or ["nothing loaded"]]
        lines += [
            f"- **Tables:** {', '.join(f'`{t}`' for t in d.tables)}",
            f"- **Source:** {d.publisher}",
            f"- **Get updates:** {d.get_updates}",
            f"- **Changes:** {d.cadence}",
            f"- **Load an update:** {d.how_to_load}",
            f"- **Terms:** {d.terms}",
        ]
        if d.notes:
            lines.append(f"- **Note:** {d.notes}")
        lines.append("")
    return "\n".join(lines)
