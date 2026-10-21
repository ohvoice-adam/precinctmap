// Per-area metric values from a results payload. Shares use valid votes (all choices that
// count, i.e. not over/under votes). Margins and leaders compare the contest-wide top two.

import type { Metric, Selection } from "./state";
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

function turnoutValue(f: FeatureResult): AreaValue {
  const reg = f.reg ?? 0;
  if (reg <= 0 || f.bal === null) return { status: "no_data", value: null, valid: 0, leader: null };
  const status = reg < LOW_VOTE_THRESHOLD ? "low" : "value";
  return { status, value: f.bal / reg, valid: f.bal, leader: null };
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
  if (ctx.metric === "turnout") return turnoutValue(f);
  if (f.v === null) {
    const status = f.bal === 0 ? "no_ballots" : "not_on_ballot";
    return { status, value: null, valid: 0, leader: null };
  }
  const valid = sum(f.v, ctx.counted);
  if (valid <= 0) return { status: "low", value: null, valid: 0, leader: null };
  const status: Status = valid < LOW_VOTE_THRESHOLD ? "low" : "value";
  return { status, valid, ...voteValue(ctx, f.v, valid) };
}
