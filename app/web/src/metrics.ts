// Per-area metric values from a results payload. Shares use valid votes (all choices that
// count, i.e. not over/under votes). Margins and leaders compare the contest-wide top two.

import type { Metric, Selection } from "./state";
import { TURNOUT_METRICS } from "./state";
import type { FeatureResult, Results } from "./types";

/** Areas with fewer valid votes than this are hatched, and the count shows in the tooltip. */
export const LOW_VOTE_THRESHOLD = 25;

export type Status = "value" | "low" | "not_on_ballot" | "no_ballots" | "no_data";

export interface AreaValue {
  status: Status;
  value: number | null; // a fraction for shares/margins/turnout, a count for totals
  valid: number;
  leader: string | null; // choice_id of the area's leader (leader metric)
}

export interface MetricContext {
  metric: Metric;
  counted: number[]; // indexes of choices that count toward valid votes
  choiceIndex: number | null; // selected candidate (share metric)
  yes: number[];
  no: number[];
  topTwo: [number, number] | null; // contest-wide leaders, by index
  rank: number[]; // contender indexes by contest-wide votes, descending
}

function contestTotals(results: Results): number[] {
  const totals = results.choices.map(() => 0);
  for (const f of Object.values(results.features)) {
    f.v?.forEach((v, i) => (totals[i] = (totals[i] ?? 0) + v));
  }
  return totals;
}

export function metricContext(results: Results, sel: Selection): MetricContext {
  const idx = (pred: (k: string, counts: boolean) => boolean): number[] =>
    results.choices.flatMap((c, i) => (pred(c.kind, c.counts) ? [i] : []));
  const counted = idx((_, counts) => counts);
  const contenders = idx((k, counts) => counts && k !== "no_petition");
  const totals = contestTotals(results);
  const rank = [...contenders].sort((a, b) => (totals[b] ?? 0) - (totals[a] ?? 0));
  const yes = idx((k) => k === "yes");
  const no = idx((k) => k === "no");
  const [a, b] = results.type === "issue" ? [yes[0], no[0]] : [rank[0], rank[1]];
  const chosen = results.choices.findIndex((c) => c.choice_id === sel.choice);
  return {
    metric: sel.metric,
    counted,
    choiceIndex: chosen >= 0 ? chosen : null,
    yes,
    no,
    topTwo: a !== undefined && b !== undefined ? [a, b] : null,
    rank,
  };
}

const sum = (v: number[], idx: number[]): number => idx.reduce((s, i) => s + (v[i] ?? 0), 0);

/** Turnout measures. `valid` is the area's ballots cast (shown as the count); `value` is:
 * turnout = ballots / registered; ballots; party_ballots = the party's ballots;
 * party_turnout = party ballots / registered; party_share = party ballots / ballots. */
function turnoutValue(ctx: MetricContext, f: FeatureResult): AreaValue {
  const none: AreaValue = { status: "no_data", value: null, valid: 0, leader: null };
  const reg = f.reg ?? 0;
  const bal = f.bal;
  if (bal === null) return none;
  const party = ctx.choiceIndex === null ? null : (f.v?.[ctx.choiceIndex] ?? 0);
  const perRegistered = ctx.metric === "turnout" || ctx.metric === "party_turnout";
  if (perRegistered && reg <= 0) return none;
  if (ctx.metric === "party_share" && bal <= 0) return { status: "no_ballots", value: null, valid: 0, leader: null };
  if (ctx.metric !== "turnout" && ctx.metric !== "ballots" && party === null) return none;
  const value =
    ctx.metric === "turnout" ? bal / reg
    : ctx.metric === "ballots" ? bal
    : ctx.metric === "party_turnout" ? (party ?? 0) / reg
    : ctx.metric === "party_share" ? (party ?? 0) / bal
    : (party ?? 0);
  const base = ctx.metric === "party_share" ? bal : perRegistered ? reg : bal;
  return { status: base < LOW_VOTE_THRESHOLD ? "low" : "value", value, valid: bal, leader: null };
}

function voteValue(ctx: MetricContext, v: number[], valid: number): Pick<AreaValue, "value" | "leader"> {
  switch (ctx.metric) {
    case "share":
      return { value: ctx.choiceIndex === null ? null : (v[ctx.choiceIndex] ?? 0) / valid, leader: null };
    case "yes_share":
      return { value: sum(v, ctx.yes) / valid, leader: null };
    case "margin":
      return {
        value: ctx.topTwo ? ((v[ctx.topTwo[0]] ?? 0) - (v[ctx.topTwo[1]] ?? 0)) / valid : null,
        leader: null,
      };
    case "leader": {
      const best = ctx.rank.reduce((m, i) => ((v[i] ?? 0) > (v[m] ?? 0) ? i : m), ctx.rank[0] ?? 0);
      return { value: (v[best] ?? 0) / valid, leader: String(best) };
    }
    default:
      return { value: valid, leader: null };
  }
}

export function areaValue(ctx: MetricContext, f: FeatureResult | undefined): AreaValue {
  if (!f) return { status: "no_data", value: null, valid: 0, leader: null };
  if (TURNOUT_METRICS.has(ctx.metric)) return turnoutValue(ctx, f);
  if (f.v === null) {
    const status = f.bal === 0 ? "no_ballots" : "not_on_ballot";
    return { status, value: null, valid: 0, leader: null };
  }
  const valid = sum(f.v, ctx.counted);
  if (valid <= 0) return { status: "low", value: null, valid: 0, leader: null };
  const status: Status = valid < LOW_VOTE_THRESHOLD ? "low" : "value";
  return { status, valid, ...voteValue(ctx, f.v, valid) };
}
