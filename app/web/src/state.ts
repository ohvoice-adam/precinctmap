// Selection state: year -> election -> contest -> metric (+ choice) -> geography.
// Lives in the URL so a view can be shared by link. Every field is resolved against the
// catalog, so a stale or hand-edited link lands on the nearest valid view.

import type { Catalog, CatalogContest, CatalogElection, Choice, Geography } from "./types";

export type Metric =
  | "share"
  | "yes_share"
  | "margin"
  | "leader"
  | "total"
  // Turnout entry (contest `<election>:turnout`; its choices are party ballots):
  | "turnout"
  | "ballots"
  | "party_turnout"
  | "party_share"
  | "party_ballots";

export interface Selection {
  year: number;
  election: string;
  contest: string;
  metric: Metric;
  choice: string | null; // the candidate ("share") or party ballot (party_* metrics)
  geography: Geography;
}

export type RawSelection = Partial<Record<"d" | "y" | "e" | "c" | "m" | "ch" | "g" | "pm", string>>;

export const METRIC_LABELS: Record<Metric, string> = {
  share: "Candidate's share",
  yes_share: "Yes share",
  margin: "Margin between the top two",
  leader: "Leader by area",
  total: "Total votes",
  turnout: "Turnout (% of registered voters)",
  ballots: "Ballots cast",
  party_turnout: "Party ballots, % of registered voters",
  party_share: "Party ballots, % of ballots cast",
  party_ballots: "Party ballots, count",
};

const PARTY_METRICS: ReadonlySet<Metric> = new Set(["party_turnout", "party_share", "party_ballots"]);
export const TURNOUT_METRICS: ReadonlySet<Metric> = new Set(["turnout", "ballots", ...PARTY_METRICS]);

/** Metrics that need a choice: a candidate, or a party ballot. */
export function usesChoice(metric: Metric): boolean {
  return metric === "share" || PARTY_METRICS.has(metric);
}

/** Choices that count toward shares, minus placeholders like "No Valid Petition Filed". */
export function contenders(contest: CatalogContest): Choice[] {
  return contest.choices.filter((c) => !["over", "under", "no_petition"].includes(c.kind));
}

export function metricsFor(contest: CatalogContest): Metric[] {
  if (contest.type === "turnout") {
    const parties = contenders(contest).length > 0;
    return ["turnout", "ballots", ...(parties ? (["party_turnout", "party_share", "party_ballots"] as Metric[]) : [])];
  }
  const many = contenders(contest).length >= 2;
  return contest.type === "issue"
    ? ["yes_share", "margin", "total"]
    : [...(["share"] as Metric[]), ...(many ? (["margin", "leader"] as Metric[]) : []), "total"];
}

function defaultContest(election: CatalogElection): CatalogContest | undefined {
  // Widest contest first (countywide races and issues), ties by ballot order. Turnout is
  // listed first but never the default: a link without a contest lands on a race.
  const races = election.contests.filter((c) => c.type !== "turnout");
  return [...(races.length ? races : election.contests)].sort((a, b) => b.precincts - a.precincts)[0];
}

function pickElection(catalog: Catalog, raw: RawSelection): CatalogElection | undefined {
  const byId = catalog.elections.find((e) => e.election_id === raw.e);
  if (byId) return byId;
  const latest = catalog.years[0];
  const year = catalog.years.find((y) => String(y) === raw.y) ?? latest;
  return catalog.elections.find((e) => e.year === year);
}

export function resolve(catalog: Catalog, raw: RawSelection): Selection | null {
  const election = pickElection(catalog, raw);
  if (!election) return null;
  const contest =
    election.contests.find((c) => c.contest_id === raw.c) ?? defaultContest(election);
  if (!contest) return null;
  const metrics = metricsFor(contest);
  const metric = metrics.find((m) => m === raw.m) ?? metrics[0] ?? "total";
  const pool = contenders(contest);
  const choice =
    usesChoice(metric) ? (pool.find((c) => c.choice_id === raw.ch) ?? pool[0])?.choice_id ?? null : null;
  const geos = election.geographies.map((g) => g.geography);
  const geography = geos.find((g) => g === raw.g) ?? geos[0] ?? "precinct";
  return { year: election.year, election: election.election_id, contest: contest.contest_id, metric, choice, geography };
}

export function toParams(sel: Selection): URLSearchParams {
  const p = new URLSearchParams({
    y: String(sel.year),
    e: sel.election,
    c: sel.contest,
    m: sel.metric,
    g: sel.geography,
  });
  if (sel.choice) p.set("ch", sel.choice);
  return p;
}

export function fromParams(search: string): RawSelection {
  const p = new URLSearchParams(search);
  const raw: RawSelection = {};
  for (const key of ["d", "y", "e", "c", "m", "ch", "g", "pm"] as const) {
    const v = p.get(key);
    if (v !== null) raw[key] = v;
  }
  return raw;
}

export function findElection(catalog: Catalog, sel: Selection): CatalogElection {
  const e = catalog.elections.find((x) => x.election_id === sel.election);
  if (!e) throw new Error(`election ${sel.election} not in catalog`);
  return e;
}

export function findContest(catalog: Catalog, sel: Selection): CatalogContest {
  const c = findElection(catalog, sel).contests.find((x) => x.contest_id === sel.contest);
  if (!c) throw new Error(`contest ${sel.contest} not in catalog`);
  return c;
}

/** A control change: one field the user just picked. */
export type Change = Partial<Pick<Selection, "election" | "contest" | "metric" | "choice" | "geography">> & {
  year?: number;
};

/** Merge a control change into the selection, dropping what no longer applies. */
export function applyChange(sel: Selection, change: Change): RawSelection {
  const base: RawSelection = { m: sel.metric, g: sel.geography };
  if (change.year !== undefined) return { ...base, y: String(change.year) };
  if (change.election) return { ...base, e: change.election };
  if (change.contest) return { ...base, e: sel.election, c: change.contest };
  return {
    ...base,
    e: sel.election,
    c: sel.contest,
    m: change.metric ?? sel.metric,
    g: change.geography ?? sel.geography,
    ...(change.choice ?? sel.choice ? { ch: change.choice ?? sel.choice ?? "" } : {}),
  };
}
