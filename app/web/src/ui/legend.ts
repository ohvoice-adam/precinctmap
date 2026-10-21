// Legend: fixed bins, then the "no number here" states so gray is never read as zero.

import { LOW_VOTE_THRESHOLD } from "../metrics";
import { LOW_PARCEL_THRESHOLD } from "../measures/model";
import type { Scale } from "../scales";
import { STATUS_COLORS } from "../map/style";
import type { Geography } from "../types";
import { el } from "./dom";
import { STATUS_TEXT } from "./format";

const LOW_TEXT = {
  results: `Fewer than ${LOW_VOTE_THRESHOLD} votes (hatched)`,
  property: `Fewer than ${LOW_PARCEL_THRESHOLD} parcels (hatched)`,
  census: "Large margin of error (hatched)",
} as const;
const EMPTY_TEXT = {
  results: `${STATUS_TEXT.not_on_ballot}, or no ballots cast`,
  property: "No residential parcels",
  census: "No estimate (no people or households)",
} as const;

function swatch(color: string, label: string, extraClass = ""): HTMLElement {
  return el(
    "li",
    {},
    el("span", { class: `swatch ${extraClass}`.trim(), style: `background:${color}`, "aria-hidden": "true" }),
    el("span", {}, label),
  );
}

/** `used`: bin indexes present on the map (categorical legends list only those). */
export function renderLegend(
  target: HTMLElement,
  scale: Scale,
  geography: Geography,
  used: Set<number>,
  dataset: "results" | "property" | "census" = "results",
): void {
  const bins = scale.kind === "categorical" ? scale.bins.filter((_, i) => used.has(i)) : [...scale.bins];
  if (scale.kind !== "categorical") bins.reverse(); // high values on top
  const states = [
    el("li", {}, el("span", { class: "swatch hatch", "aria-hidden": "true" }),
      el("span", {}, LOW_TEXT[dataset])),
    swatch(STATUS_COLORS.not_on_ballot, EMPTY_TEXT[dataset], "outlined"),
    geography === "council_district"
      ? el("li", {}, el("span", { class: "swatch hatch-back", "aria-hidden": "true" }), el("span", {}, STATUS_TEXT.not_in_columbus))
      : null,
    swatch(STATUS_COLORS.outside_county, "Outside Franklin County: no data", "outlined"),
  ];
  target.replaceChildren(
    el("h2", { class: "legend-title" }, scale.title),
    el("ul", { class: "legend-bins" }, ...bins.map((b) => swatch(b.color, b.label))),
    el("ul", { class: "legend-states" }, ...states),
  );
}
