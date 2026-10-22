// Selection controls. Each lists only options that have data (the catalog only holds those).

import type { Change, Metric, Selection } from "../state";
import { METRIC_LABELS, contenders, findContest, findElection, metricsFor, usesChoice } from "../state";
import type { Catalog, CatalogContest, Geography } from "../types";
import { el, labeled, option } from "./dom";


const PARTY_GROUPS: Record<string, string> = {
  Dem: "Democratic ballot",
  Rep: "Republican ballot",
  Lib: "Libertarian ballot",
  Grn: "Green ballot",
};

function select(onChange: (value: string) => void): HTMLSelectElement {
  const s = el("select");
  s.addEventListener("change", () => { onChange(s.value); });
  return s;
}

function contestGroups(contests: CatalogContest[], filter: string): Map<string, CatalogContest[]> {
  const groups = new Map<string, CatalogContest[]>();
  const needle = filter.trim().toLowerCase();
  for (const c of contests) {
    if (needle && !c.name.toLowerCase().includes(needle)) continue;
    const key =
      c.type === "turnout" ? "Turnout"
      : c.party ? (PARTY_GROUPS[c.party] ?? `${c.party} ballot`)
      : c.type === "issue" ? "Issues" : "Nonpartisan and general";
    groups.set(key, [...(groups.get(key) ?? []), c]);
  }
  return groups;
}

export class Controls {
  readonly root = el("form", { class: "controls", "aria-label": "Map selection" });
  private readonly year = select((v) => {
    this.emit({ year: Number(v) });
  });
  private readonly election = select((v) => {
    this.emit({ election: v });
  });
  private readonly search = el("input", { type: "search", placeholder: "Filter contests", "aria-label": "Filter contests" });
  private readonly contest = select((v) => {
    this.emit({ contest: v });
  });
  private readonly metric = select((v) => {
    this.emit({ metric: v as Metric });
  });
  private readonly choice = select((v) => {
    this.emit({ choice: v });
  });
  private readonly choiceField: HTMLElement;
  private readonly geography = select((v) => {
    this.emit({ geography: v as Geography });
  });
  private last: { catalog: Catalog; sel: Selection } | null = null;

  constructor(private readonly emit: (change: Change) => void) {
    this.root.addEventListener("submit", (e) => { e.preventDefault(); });
    this.search.addEventListener("input", () => {
      if (this.last) this.fillContests(this.last.catalog, this.last.sel);
    });
    this.choiceField = labeled("Candidate", this.choice, "ctl-choice");
    this.root.append(
      labeled("Year", this.year, "ctl-year"),
      labeled("Election", this.election, "ctl-election"),
      el("div", { class: "field" }, el("label", { for: "ctl-contest" }, "Contest"), this.search, this.contest),
      labeled("Show", this.metric, "ctl-metric"),
      this.choiceField,
      labeled("Map by", this.geography, "ctl-geography"),
    );
    this.contest.id = "ctl-contest";
  }

  render(catalog: Catalog, sel: Selection): void {
    this.last = { catalog, sel };
    const election = findElection(catalog, sel);
    const contest = findContest(catalog, sel);
    this.year.replaceChildren(...catalog.years.map((y) => option(String(y), String(y), y === sel.year)));
    this.election.replaceChildren(
      ...catalog.elections
        .filter((e) => e.year === sel.year)
        .map((e) => option(e.election_id, `${e.label}${e.certified ? "" : " (unofficial)"}`, e.election_id === sel.election)),
    );
    this.fillContests(catalog, sel);
    this.metric.replaceChildren(
      ...metricsFor(contest).map((m) => option(m, METRIC_LABELS[m], m === sel.metric)),
    );
    const turnout = contest.type === "turnout";
    this.choiceField.hidden = !usesChoice(sel.metric);
    const label = this.choiceField.querySelector("label");
    if (label) label.textContent = turnout ? "Party ballot" : "Candidate";
    this.choice.replaceChildren(
      ...contenders(contest).map((c) =>
        option(c.choice_id, c.party && !turnout ? `${c.name} (${c.party})` : c.name, c.choice_id === sel.choice)),
    );
    this.geography.replaceChildren(
      ...election.geographies.map((g) => option(g.geography, g.label, g.geography === sel.geography)),
    );
  }

  private fillContests(catalog: Catalog, sel: Selection): void {
    const election = findElection(catalog, sel);
    const groups = contestGroups(election.contests, this.search.value);
    const nodes: HTMLElement[] = [];
    for (const [label, contests] of groups) {
      nodes.push(el("optgroup", { label }, ...contests.map((c) => option(c.contest_id, c.name, c.contest_id === sel.contest))));
    }
    const shown = [...groups.values()].flat().some((c) => c.contest_id === sel.contest);
    if (!shown) nodes.unshift(option(sel.contest, findContest(catalog, sel).name, true)); // keep current visible
    this.contest.replaceChildren(...nodes);
  }
}
