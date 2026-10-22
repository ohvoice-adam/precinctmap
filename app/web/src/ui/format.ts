// Plain-language text for tooltips and the legend. Sentence case; numbers rounded for
// reading (allocated votes are fractional estimates).

import type { AreaValue } from "../metrics";
import { LOW_VOTE_THRESHOLD } from "../metrics";
import type { Metric } from "../state";
import { TURNOUT_METRICS } from "../state";
import type { Results } from "../types";

export const METHOD_TEXT: Record<string, string> = {
  exact: "Exact: every precinct lies wholly inside this area.",
  allocated: "Estimated: built from parts of split precincts, weighted by 2020 census block population.",
  mixed: "Mostly exact; some precincts are split and their share is estimated by 2020 census block population.",
};

export const STATUS_TEXT = {
  not_on_ballot: "Contest not on the ballot here",
  no_ballots: "No ballots cast here",
  no_data: "No data",
  not_in_columbus: "Not in Columbus (no council district)",
  outside_county: "No data: outside Franklin County",
} as const;

export function votes(n: number): string {
  return Math.round(n).toLocaleString("en-US");
}

export function percent(x: number, digits = 1): string {
  return `${(x * 100).toFixed(digits)}%`;
}

/** `choice`: the selected candidate or party ballot's name (party_* metrics). */
export function metricText(metric: Metric, a: AreaValue, results: Results, sides: [string, string], choice = ""): string {
  if (a.value === null) return "";
  switch (metric) {
    case "total":
      return `${votes(a.value)} valid votes`;
    case "turnout":
      return `${percent(a.value)} turnout`;
    case "ballots":
      return `${votes(a.value)} ballots cast`;
    case "party_ballots":
      return `${votes(a.value)} ${choice.toLowerCase()}`;
    case "party_turnout":
      return `${choice}: ${percent(a.value)} of registered voters`;
    case "party_share":
      return `${choice}: ${percent(a.value)} of ballots cast`;
    case "margin": {
      const pts = (Math.abs(a.value) * 100).toFixed(1);
      return a.value === 0 ? "Tied" : `${a.value > 0 ? sides[0] : sides[1]} ahead by ${pts} points`;
    }
    case "leader": {
      const name = results.choices[Number(a.leader)]?.name ?? "?";
      return `${name} leads with ${percent(a.value)}`;
    }
    default:
      return percent(a.value);
  }
}

/** Tooltip lines for an area: name, then the value (or why there is none), then the count. */
export function tooltipLines(
  name: string,
  metric: Metric,
  a: AreaValue,
  results: Results,
  sides: [string, string],
  method?: string | null,
  choice = "",
): string[] {
  const lines = [name];
  if (a.status === "not_on_ballot" || a.status === "no_ballots" || a.status === "no_data") {
    lines.push(STATUS_TEXT[a.status]);
    return lines;
  }
  const text = metricText(metric, a, results, sides, choice);
  if (text) lines.push(text);
  const turnout = TURNOUT_METRICS.has(metric);
  if (metric !== "total" && metric !== "ballots") lines.push(`${votes(a.valid)} ${turnout ? "ballots cast" : "valid votes"}`);
  const few = metric === "party_share" || metric === "ballots" || metric === "party_ballots" ? "ballots" : turnout ? "registered voters" : "votes";
  if (a.status === "low") lines.push(`Fewer than ${LOW_VOTE_THRESHOLD} ${few}: read with care`);
  if (method === "allocated" || method === "mixed") lines.push("Includes estimates from split precincts");
  return lines;
}

/** For margins, the legend and tooltips name the sides; this resolves "first"/"second". */
export function marginSides(results: Results, topTwo: [number, number] | null): [string, string] {
  if (!topTwo) return ["?", "?"];
  return [results.choices[topTwo[0]]?.name ?? "?", results.choices[topTwo[1]]?.name ?? "?"];
}
