// MapLibre paint expressions driven by feature-state {status, bin}. Status colors are
// neutral grays: they mark "no number here" and never look like a data value.

import type { ExpressionSpecification } from "maplibre-gl";

// White = "no vote here"; the light gray "close" bin is the only gray that is data.
export const STATUS_COLORS = {
  not_on_ballot: "#ffffff",
  no_ballots: "#ffffff",
  no_data: "#ffffff",
  not_in_columbus: "#f1f0ec", // plus a 135° hatch
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

/** Hairline hatch for fill-pattern: 45° marks low vote counts, 135° marks "not in Columbus". */
export function hatchImage(mirror = false, size = 8): { width: number; height: number; data: Uint8Array } {
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const d = mirror ? (x - y + size) % size : (x + y) % size;
      if (d === 0 || d === size - 1) {
        const o = (y * size + x) * 4;
        data.set([82, 81, 78, mirror ? 70 : 150], o); // secondary ink; the 135° context hatch is lighter
      }
    }
  }
  return { width: size, height: size, data };
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
