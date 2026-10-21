import type { LngLatBoundsLike } from "maplibre-gl";

/** Franklin County, OH extent (TIGER 2026, GEOID 39049), EPSG:4326 [west, south, east, north]. */
export const FRANKLIN_BOUNDS: [number, number, number, number] = [
  -83.2609, 39.795, -82.7618, 40.1431,
];

/** TIGER internal point for Franklin County. */
export const FRANKLIN_CENTER: [number, number] = [-83.0091, 39.9699];

/** No-tracking basemap with no API key (OpenFreeMap). Muted so the choropleth carries the color. */
export const BASEMAP_STYLE_URL = "https://tiles.openfreemap.org/styles/positron";

/** Initial view: fit the county with padding; allow panning a little past it. */
export function initialView(): { bounds: LngLatBoundsLike; maxBounds: LngLatBoundsLike } {
  const [w, s, e, n] = FRANKLIN_BOUNDS;
  const padX = (e - w) * 0.5;
  const padY = (n - s) * 0.5;
  return {
    bounds: FRANKLIN_BOUNDS,
    maxBounds: [w - padX, s - padY, e + padX, n + padY],
  };
}
