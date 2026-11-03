// Legend: fixed bins with area counts, then the "no number here" states.

import { LOW_VOTE_THRESHOLD } from "../metrics";
import { LOW_PARCEL_THRESHOLD } from "../measures/model";
import type { Scale } from "../scales";
import type { AreaState } from "../map/view";
import { STATUS_COLORS, dotsImage, hatchImage, patternBackground } from "../map/style";
import type { Geography } from "../types";
import { compact, el } from "./dom";
import { STATUS_TEXT } from "./format";

const LOW_TEXT = {
  results: `Fewer than ${LOW_VOTE_THRESHOLD} votes (hatched)`,
  turnout: `Fewer than ${LOW_VOTE_THRESHOLD} registered voters or ballots (hatched)`,
  property: `Fewer than ${LOW_PARCEL_THRESHOLD} parcels (hatched)`,
  census: "Large margin of error (hatched)",
} as const;
const EMPTY_TEXT = {
  results: `${STATUS_TEXT.not_on_ballot}, or no ballots cast`,
  turnout: "No ballots cast, or no registered voters",
  property: "No residential parcels",
  census: "No estimate (no people or households)",
} as const;

const AREA_NOUN: Record<Geography, string> = {
  precinct: "precincts",
  ward: "wards",
  council_district: "districts",
  municipality: "areas",
  zcta: "ZIP code areas",
};

/** One legend row. `count` draws a bar (length relative to `max`) and the area count beside it;
 * rows without a count show a plain swatch. `background` is a color or a map pattern tile. */
function row(background: string, label: string, count: number | null, max: number, extraClass = "", minPx = 4): HTMLElement {
  const pct = count === null ? 0 : (100 * count) / Math.max(max, 1);
  const width = count === null ? null : count > 0 ? `max(${minPx}px, ${pct.toFixed(1)}%)` : "0";
  return el(
    "li",
    { class: count === null ? "plain" : "" },
    el("span", { class: "r" }, label),
    el("span", { class: "track", "aria-hidden": "true" },
      el("span", { class: `swatch ${extraClass}`.trim(), style: `background:${background}${width ? `;width:${width}` : ""}` })),
    el("span", { class: "c" }, count === null ? "" : count.toLocaleString("en-US")),
  );
}

/** Legend as a histogram: each color bin with the number of areas in it (counted from the same
 * states the map paints), then the "no number here" states so white is never read as zero. */
export function renderLegend(
  target: HTMLElement,
  scale: Scale,
  geography: Geography,
  states: Map<string, AreaState>,
  dataset: "results" | "turnout" | "property" | "census" = "results",
  base?: string, // property: what the hatch threshold counts, when not parcels
): void {
  const counts = new Map<number, number>();
  let low = 0;
  let empty = 0;
  for (const s of states.values()) {
    if (s.bin >= 0) counts.set(s.bin, (counts.get(s.bin) ?? 0) + 1);
    if (s.status === "low") low += 1;
    else if (s.bin < 0) empty += 1;
  }
  const indexed = scale.bins.map((b, i) => ({ ...b, i }));
  const bins = scale.kind === "categorical" ? indexed.filter((b) => counts.has(b.i)) : indexed.reverse(); // high values on top
  const max = Math.max(0, ...counts.values(), low);
  const states_ = compact(
    row(patternBackground(hatchImage(), "#ffffff"), base && dataset === "property" ? `Fewer than ${LOW_PARCEL_THRESHOLD} ${base} (hatched)` : LOW_TEXT[dataset], low, max, "", 24), // wide enough to show the hatch
    row(STATUS_COLORS.not_on_ballot, EMPTY_TEXT[dataset], empty, max, "outlined", 12),
    geography === "council_district"
      ? row(patternBackground(dotsImage(), STATUS_COLORS.not_in_columbus), STATUS_TEXT.not_in_columbus, null, max)
      : null,
    row(STATUS_COLORS.outside_county, "Outside Franklin County: no data", null, max, "outlined"),
  );
  target.replaceChildren(
    el("div", { class: "legend-head" }, el("h2", { class: "legend-title" }, scale.title), el("span", { class: "legend-unit" }, AREA_NOUN[geography])),
    el("ul", { class: "legend-bins" }, ...bins.map((b) => row(b.color, b.label, counts.get(b.i) ?? 0, max))),
    el("ul", { class: "legend-states" }, ...states_),
  );
}
