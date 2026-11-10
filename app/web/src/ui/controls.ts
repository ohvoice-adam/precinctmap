// Selection controls. Each lists only options that have data (the catalog only holds those).

import type { Change, Metric, ScaleMode, Selection } from "../state";
import { METRIC_LABELS, canFit, contenders, findContest, findElection, metricsFor, usesChoice } from "../state";
import type { Catalog, CatalogContest, Geography } from "../types";
import { el, option } from "./dom";
import { ChipGroup, Picker, step } from "./steps";

const PARTY_GROUPS: Record<string, string> = {
  Dem: "Democratic ballot",
  Rep: "Republican ballot",
  Lib: "Libertarian ballot",
  Grn: "Green ballot",
};

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

/** The election steps, in drill-down order: year, election, contest, what to map, geography. */
export class Controls {
  readonly root = el("form", { class: "controls steps", "aria-label": "Map selection" });
  private readonly year = new Picker("ctl-year", (v) => { this.emit({ year: Number(v) }); });
  private readonly election = new Picker("ctl-election", (v) => { this.emit({ election: v }); });
  private readonly search = el("input", { type: "search", class: "filter", placeholder: "Filter contests", "aria-label": "Filter contests" });
  private readonly contest = new Picker("ctl-contest", (v) => { this.emit({ contest: v }); }, true);
  private readonly metric = new ChipGroup("ctl-metric", (v) => { this.emit({ metric: v as Metric }); });
  private readonly choice = new Picker("ctl-choice", (v) => { this.emit({ choice: v }); });
  private readonly choiceLabel = el("label", { class: "sub-label", for: "ctl-choice" }, "Candidate");
  private readonly choiceField = el("div", { class: "subfield" }, this.choiceLabel, this.choice.root);
  private readonly scale = new ChipGroup("ctl-scale", (v) => { this.emit({ scale: v as ScaleMode }); }, true);
  private readonly scaleField = el("div", { class: "subfield" },
    el("span", { class: "sub-label", id: "ctl-scale-label" }, "Color scale"), this.scale.root);
  private readonly geography = new ChipGroup("ctl-geography", (v) => { this.emit({ geography: v as Geography }); });
  private last: { catalog: Catalog; sel: Selection } | null = null;

  constructor(private readonly emit: (change: Change) => void) {
    this.root.addEventListener("submit", (e) => { e.preventDefault(); });
    this.search.addEventListener("input", () => {
      if (this.last) this.fillContests(this.last.catalog, this.last.sel);
    });
    this.root.append(
      step(1, "Year", "ctl-year", this.year.root),
      step(2, "Election", "ctl-election", this.election.root),
      step(3, "Contest", "ctl-contest", this.contest.root, this.search),
      step(4, "What to map", "ctl-metric", this.metric.root, this.choiceField, this.scaleField),
      step(5, "Map by", "ctl-geography", this.geography.root),
    );
  }

  render(catalog: Catalog, sel: Selection): void {
    this.last = { catalog, sel };
    const election = findElection(catalog, sel);
    const contest = findContest(catalog, sel);
    this.year.select.replaceChildren(...catalog.years.map((y) => option(String(y), String(y), y === sel.year)));
    this.year.sync();
    this.election.select.replaceChildren(
      ...catalog.elections
        .filter((e) => e.year === sel.year)
        .map((e) => option(e.election_id, `${e.label}${e.certified ? "" : " (unofficial)"}`, e.election_id === sel.election)),
    );
    this.election.sync();
    this.fillContests(catalog, sel);
    this.metric.render(metricsFor(contest).map((m) => ({ value: m, label: METRIC_LABELS[m] })), sel.metric);
    const turnout = contest.type === "turnout";
    this.choiceField.hidden = !usesChoice(sel.metric);
    this.choiceLabel.textContent = turnout ? "Party ballot" : "Candidate";
    this.choice.select.replaceChildren(
      ...contenders(contest).map((c) =>
        option(c.choice_id, c.party && !turnout ? `${c.name} (${c.party})` : c.name, c.choice_id === sel.choice)),
    );
    this.choice.sync();
    // Fixed bins run 0-100% for every candidate; fitted bins follow this one's own spread, so a
    // minor candidate's geography shows. Offered wherever a single candidate or party is mapped.
    this.scaleField.hidden = !canFit(sel.metric);
    const what = turnout ? "party ballot" : "candidate";
    this.scale.render([{ value: "fixed", label: "Fixed bins" }, { value: "relative", label: `Fit to this ${what}` }], sel.scale);
    this.geography.render(election.geographies.map((g) => ({ value: g.geography, label: g.label })), sel.geography);
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
    this.contest.select.replaceChildren(...nodes);
    this.contest.sync(true);
  }
}
