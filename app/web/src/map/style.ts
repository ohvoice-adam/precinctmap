// MapLibre paint expressions driven by feature-state {status, bin}. Status colors are
// neutral grays: they mark "no number here" and never look like a data value.

import type { ExpressionSpecification } from "maplibre-gl";

// White = "no vote here"; the light gray "close" bin is the only gray that is data.
export const STATUS_COLORS = {
  not_on_ballot: "#ffffff",
  no_ballots: "#ffffff",
  no_data: "#ffffff",
  not_in_columbus: "#f1f0ec", // plus a dot pattern (dotsImage)
  outside_county: "#f4f3ef",
} as const;

export const OUTLINE = "#ffffff";
export const HOVER_OUTLINE = "#1f2933"; // interface ink: chrome, not a data color

export function fillColor(binColors: string[]): ExpressionSpecification {
  const status: ExpressionSpecification = ["feature-state", "status"];
  // MapLibre's types cannot express a variadic match built at runtime; the shape is checked
  // by MapLibre when the paint property is set.
  const match =
    binColors.length > 0
      ? (["match", ["feature-state", "bin"], ...binColors.flatMap((c, i) => [i, c]), STATUS_COLORS.no_data] as unknown as ExpressionSpecification)
      : (["literal", STATUS_COLORS.no_data] as ExpressionSpecification);
  return [
    "case",
    ["any", ["==", status, "value"], ["==", status, "low"]],
    match,
    ["==", status, "not_on_ballot"],
    STATUS_COLORS.not_on_ballot,
    ["==", status, "no_ballots"],
    STATUS_COLORS.no_ballots,
    STATUS_COLORS.no_data,
  ];
}

export const FILL_OPACITY: ExpressionSpecification = [
  "case",
  ["==", ["feature-state", "status"], "low"],
  0.45,
  0.88,
];

export const HATCH_OPACITY: ExpressionSpecification = [
  "case",
  ["==", ["feature-state", "status"], "low"],
  1,
  0,
];

export const LINE_COLOR: ExpressionSpecification = [
  "case",
  ["any", ["boolean", ["feature-state", "hover"], false], ["boolean", ["feature-state", "selected"], false]],
  HOVER_OUTLINE,
  OUTLINE,
];

export const LINE_WIDTH: ExpressionSpecification = [
  "case",
  ["boolean", ["feature-state", "selected"], false],
  2.5,
  ["boolean", ["feature-state", "hover"], false],
  1.8,
  0.6,
];

export interface PatternImage {
  width: number;
  height: number;
  data: Uint8Array; // RGBA, rows top to bottom
}

const PATTERN_INK = [82, 81, 78] as const; // secondary ink

function tile(size: number, lit: (x: number, y: number) => boolean, alpha: number): PatternImage {
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) if (lit(x, y)) data.set([...PATTERN_INK, alpha], (y * size + x) * 4);
  }
  return { width: size, height: size, data };
}

/** Low counts: a hairline diagonal hatch rising left to right ("/"). The only diagonal pattern. */
export function hatchImage(size = 8): PatternImage {
  return tile(size, (x, y) => (x + y) % size === 0 || (x + y) % size === size - 1, 150);
}

/** "Not in Columbus": a staggered grid of 2 px dots, so it never reads as the low-count hatch. */
export function dotsImage(size = 8): PatternImage {
  const half = size / 2;
  const dot = (x: number, y: number, cx: number, cy: number): boolean => x >= cx && x < cx + 2 && y >= cy && y < cy + 2;
  return tile(size, (x, y) => dot(x, y, 1, 1) || dot(x, y, 1 + half, 1 + half), 110);
}

/** A CSS background drawing `img` exactly as the map does (1 image px = 1 CSS px) over `base`,
 * so legend swatches can never drift from the map's patterns. */
export function patternBackground(img: PatternImage, base: string): string {
  const rects: string[] = [];
  for (let y = 0; y < img.height; y++) {
    for (let x = 0; x < img.width; x++) {
      const o = (y * img.width + x) * 4;
      const a = img.data[o + 3] ?? 0;
      if (a === 0) continue;
      const rgb = `rgb(${img.data[o] ?? 0},${img.data[o + 1] ?? 0},${img.data[o + 2] ?? 0})`;
      rects.push(`<rect x='${x}' y='${y}' width='1' height='1' fill='${rgb}' fill-opacity='${(a / 255).toFixed(3)}'/>`);
    }
  }
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${img.width}' height='${img.height}' shape-rendering='crispEdges'>${rects.join("")}</svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}") 0 0 / ${img.width}px ${img.height}px repeat ${base}`;
}

/** A world polygon with the county cut out: covers everything outside Franklin County. */
export function outsideMask(county: GeoJSON.Geometry): GeoJSON.Feature<GeoJSON.Polygon> {
  const world: GeoJSON.Position[] = [[-179, -85], [179, -85], [179, 85], [-179, 85], [-179, -85]];
  const holes: GeoJSON.Position[][] =
    county.type === "Polygon"
      ? [county.coordinates[0] ?? []]
      : county.type === "MultiPolygon"
        ? county.coordinates.map((p) => p[0] ?? [])
        : [];
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [world, ...holes] } };
}
