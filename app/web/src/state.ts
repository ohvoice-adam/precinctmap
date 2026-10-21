// Selection state: year -> election -> contest -> metric (+ choice) -> geography.
// Lives in the URL so a view can be shared by link. Every field is resolved against the
// catalog, so a stale or hand-edited link lands on the nearest valid view.

import type { Catalog, CatalogContest, CatalogElection, Choice, Geography } from "./types";

export type Metric = "share" | "yes_share" | "margin" | "leader" | "total" | "turnout";

export interface Selection {
  year: number;
  election: string;
  contest: string;
  metric: Metric;
  choice: string | null; // only for the candidate "share" metric
  geography: Geography;
}

export type RawSelection = Partial<Record<"d" | "y" | "e" | "c" | "m" | "ch" | "g" | "pm", string>>;

export const METRIC_LABELS: Record<Metric, string> = {
  share: "Candidate's share",
  yes_share: "Yes share",
  margin: "Margin between the top two",
  leader: "Leader by area",
  total: "Total votes",
  turnout: "Turnout",
};

/** Choices that count toward shares, minus placeholders like "No Valid Petition Filed". */
export function contenders(contest: CatalogContest): Choice[] {
  return contest.choices.filter((c) => !["over", "under", "no_petition"].includes(c.kind));
}

export function metricsFor(contest: CatalogContest, election: CatalogElection): Metric[] {
  const hasTurnout = election.turnout_parties.includes("ALL");
  const many = contenders(contest).length >= 2;
  const metrics: Metric[] =
    contest.type === "issue"
      ? ["yes_share", "margin", "total"]
      : [...(["share"] as Metric[]), ...(many ? (["margin", "leader"] as Metric[]) : []), "total"];
  return hasTurnout ? [...metrics, "turnout"] : metrics;
}

function defaultContest(election: CatalogElection): CatalogContest | undefined {
  // Widest contest first (countywide races and issues), ties by ballot order.
  return [...election.contests].sort((a, b) => b.precincts - a.precincts)[0];
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
  const metrics = metricsFor(contest, election);
  const metric = metrics.find((m) => m === raw.m) ?? metrics[0] ?? "total";
  const pool = contenders(contest);
  const choice =
    metric === "share" ? (pool.find((c) => c.choice_id === raw.ch) ?? pool[0])?.choice_id ?? null : null;
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
