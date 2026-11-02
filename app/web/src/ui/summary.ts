// The result under the steps: the contest's totals across the mapped areas, drawn as bars.
// Issues get a for/against split, candidate contests their top three, turnout the county rate.

import type { MetricContext } from "../metrics";
import { contestTotals } from "../metrics";
import type { Results } from "../types";
import { compact, el } from "./dom";
import { percent, votes } from "./format";

const TOP = 3;

/** "Franklin County" unless areas were excluded (council districts cover Columbus only). */
function scope(results: Results): string {
  return (results.totals.excluded ?? 0) > 0 ? "In the mapped areas" : "Franklin County";
}

function split(yesName: string, noName: string, yes: number, no: number): HTMLElement[] {
  const total = yes + no;
  const share = total > 0 ? yes / total : 0;
  return [
    el("div", { class: "split", role: "img", "aria-label": `${yesName} ${percent(share)}, ${noName} ${percent(1 - share)}` },
      el("span", { class: "split-a", style: `width:${(100 * share).toFixed(1)}%` }, percent(share)),
      el("span", { class: "split-b" }, percent(1 - share))),
    el("div", { class: "split-counts" }, el("span", {}, `${votes(yes)} ${yesName.toLowerCase()}`), el("span", {}, `${votes(no)} ${noName.toLowerCase()}`)),
  ];
}

function leaders(results: Results, ctx: MetricContext, totals: number[]): (Node | string)[] {
  const valid = ctx.counted.reduce((s, i) => s + (totals[i] ?? 0), 0);
  const rows = ctx.rank.slice(0, TOP).map((i) => {
    const c = results.choices[i];
    const v = totals[i] ?? 0;
    const share = valid > 0 ? v / valid : 0;
    return el("li", {},
      el("span", { class: "who" }, c?.party ? `${c.name} (${c.party})` : (c?.name ?? "")),
      el("span", { class: "share" }, percent(share)),
      el("span", { class: "track", "aria-hidden": "true" }, el("span", { class: "fill", style: `width:${(100 * share).toFixed(1)}%` })),
      el("span", { class: "votes" }, `${votes(v)} votes`));
  });
  const more = ctx.rank.length - TOP;
  return compact(el("ol", { class: "leaders" }, ...rows), more > 0 ? el("p", { class: "small" }, `and ${more} more ${more === 1 ? "choice" : "choices"}`) : null);
}

function turnout(results: Results): HTMLElement[] {
  let reg = 0;
  let bal = 0;
  for (const f of Object.values(results.features)) {
    reg += f.reg ?? 0;
    bal += f.bal ?? 0;
  }
  if (reg <= 0) return [];
  return [
    el("p", { class: "headline" }, el("b", {}, percent(bal / reg)), " turnout"),
    el("p", { class: "small" }, `${votes(bal)} ballots from ${votes(reg)} registered voters`),
  ];
}

export function renderResultSummary(target: HTMLElement, results: Results, ctx: MetricContext): void {
  const totals = contestTotals(results);
  const [yes, no] = [ctx.yes[0], ctx.no[0]];
  let body: (Node | string)[];
  if (results.type === "turnout") body = turnout(results);
  else if (results.type === "issue" && yes !== undefined && no !== undefined) {
    body = split(results.choices[yes]?.name ?? "Yes", results.choices[no]?.name ?? "No", totals[yes] ?? 0, totals[no] ?? 0);
  } else body = leaders(results, ctx, totals);
  target.replaceChildren(
    ...compact(
      el("p", { class: "scope" }, scope(results)),
      ...body,
      results.vote_for && results.vote_for > 1 ? el("p", { class: "small" }, `Vote for ${results.vote_for}: shares are of all votes cast, not of voters.`) : null,
    ),
  );
}
