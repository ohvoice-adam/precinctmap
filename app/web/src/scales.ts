// Fixed bins and palettes. Never party red/blue: magnitudes use a teal ramp, polarity uses
// purple <-> orange around a gray midpoint, leaders use orange / aqua / violet + gray.
// Validated with the dataviz palette validator; results in project-docs/palette.md.

import type { MetricContext } from "./metrics";
import type { Results } from "./types";

export interface Bin {
  from: number;
  to: number;
  color: string;
  label: string;
}

export interface Scale {
  kind: "sequential" | "diverging" | "categorical";
  title: string;
  bins: Bin[];
}

export const SEQUENTIAL = [
  "#d3eee7", "#a9dccf", "#7cc7b5", "#52b09a", "#33957f", "#227866", "#165b4e", "#0c4037",
];
// Arm A (orange) is the first-named side; arm B (purple) the second; gray is "close".
const ARM_A = ["#f7c58a", "#e08214", "#a14d07"];
const ARM_B = ["#c9c1e0", "#8d7fbf", "#542788"];
const NEUTRAL = "#e6e5e1";
export const LEADER_COLORS = ["#eb6834", "#1baf7a", "#6250d6"];
export const OTHER_COLOR = "#b8b6ae";

const pct = (x: number): string => `${Math.round(x * 100)}%`;

function bins(edges: number[], colors: string[], fmt: (x: number) => string, openTop = false): Bin[] {
  return colors.map((color, i) => {
    const from = edges[i] ?? 0;
    const to = edges[i + 1] ?? from;
    const label = openTop && i === colors.length - 1 ? `${fmt(from)}+` : `${fmt(from)}–${fmt(to)}`;
    return { from, to, color, label };
  });
}

const SHARE_EDGES = [0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0001];
const TURNOUT_EDGES = [0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0001];
const TOTAL_EDGES = [0, 100, 250, 500, 1000, 2500, 5000, 10000, Number.POSITIVE_INFINITY];
// One party's ballots over all registered voters: primary-ballot shares are usually small.
const PARTY_TURNOUT_EDGES = [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 1.0001];
const YES_EDGES = [0, 0.2, 0.35, 0.45, 0.55, 0.65, 0.8, 1.0001];
const MARGIN_EDGES = [-1.0001, -0.3, -0.15, -0.05, 0.05, 0.15, 0.3, 1.0001];
const DIVERGING = [...ARM_B].reverse().concat([NEUTRAL], ARM_A);

function marginLabel(x: number): string {
  const p = Math.round(Math.abs(x) * 100);
  return x === 0 ? "0" : `${p}`;
}

function marginBins(nameA: string, nameB: string): Bin[] {
  const out = bins(MARGIN_EDGES, DIVERGING, marginLabel);
  return out.map((b, i) => {
    if (i === 3) return { ...b, label: "Within 5 points" };
    const lead = i > 3 ? nameA : nameB;
    const lo = Math.round(Math.min(Math.abs(b.from), Math.abs(b.to)) * 100);
    const hi = Math.round(Math.max(Math.abs(b.from), Math.abs(b.to)) * 100);
    return { ...b, label: hi >= 100 ? `${lead} by ${lo}+` : `${lead} by ${lo}–${hi}` };
  });
}

function leaderBins(ctx: MetricContext, results: Results): Bin[] {
  const top = ctx.rank.slice(0, LEADER_COLORS.length);
  const out = top.map((i, k) => ({
    from: i,
    to: i,
    color: LEADER_COLORS[k] ?? OTHER_COLOR,
    label: results.choices[i]?.name ?? "?",
  }));
  if (ctx.rank.length > top.length) out.push({ from: -1, to: -1, color: OTHER_COLOR, label: "Another candidate" });
  return out;
}

export function scaleFor(ctx: MetricContext, results: Results): Scale {
  const name = (i: number | undefined): string => (i === undefined ? "?" : results.choices[i]?.name ?? "?");
  switch (ctx.metric) {
    case "share":
      return { kind: "sequential", title: `${name(ctx.choiceIndex ?? undefined)}, share of votes`, bins: bins(SHARE_EDGES, SEQUENTIAL, pct) };
    case "yes_share":
      return { kind: "diverging", title: "Yes share of votes", bins: bins(YES_EDGES, [...ARM_B].reverse().concat([NEUTRAL], ARM_A), pct) };
    case "margin": {
      const [a, b] = ctx.topTwo ?? [undefined, undefined];
      return { kind: "diverging", title: `Margin: ${name(a)} vs. ${name(b)} (points)`, bins: marginBins(name(a), name(b)) };
    }
    case "leader":
      return { kind: "categorical", title: "Leader", bins: leaderBins(ctx, results) };
    case "turnout":
      return { kind: "sequential", title: "Turnout (ballots ÷ registered)", bins: bins(TURNOUT_EDGES, SEQUENTIAL, pct) };
    case "ballots":
      return { kind: "sequential", title: "Ballots cast", bins: bins(TOTAL_EDGES, SEQUENTIAL, (x) => x.toLocaleString(), true) };
    case "party_ballots":
      return { kind: "sequential", title: name(ctx.choiceIndex ?? undefined), bins: bins(TOTAL_EDGES, SEQUENTIAL, (x) => x.toLocaleString(), true) };
    case "party_turnout":
      return { kind: "sequential", title: `${name(ctx.choiceIndex ?? undefined)} ÷ registered voters`, bins: bins(PARTY_TURNOUT_EDGES, SEQUENTIAL, pct) };
    case "party_share":
      return { kind: "sequential", title: `${name(ctx.choiceIndex ?? undefined)} ÷ all ballots`, bins: bins(SHARE_EDGES, SEQUENTIAL, pct) };
    default:
      return { kind: "sequential", title: "Valid votes", bins: bins(TOTAL_EDGES, SEQUENTIAL, (x) => x.toLocaleString(), true) };
  }
}

/** Bin index for a value (or leader choice index); -1 when nothing fits. */
export function binOf(scale: Scale, value: number | null, leader: string | null): number {
  if (scale.kind === "categorical") {
    const i = scale.bins.findIndex((b) => b.from === Number(leader));
    return i >= 0 ? i : scale.bins.findIndex((b) => b.from === -1);
  }
  if (value === null) return -1;
  return scale.bins.findIndex((b) => value >= b.from && value < b.to);
}
