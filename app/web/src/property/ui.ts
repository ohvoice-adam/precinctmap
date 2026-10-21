// Property layer UI: controls (metric, geography), detail panel, sidebar notes and export.

import { compact, el, labeled, option } from "../ui/dom";
import type { PropertyCatalog, PropertyDetail, PropertySelection, PropertyStats } from "./model";
import { formatValue } from "./model";

const GROUPS: [string, (m: string) => boolean][] = [
  ["Rentals and ownership", (m) => /rental|llc|owner|residential_parcels|apartment/.test(m)],
  ["Housing units", (m) => /^housing_units$/.test(m)],
  ["Valuation", (m) => /value/.test(m)],
  ["Construction grade", (m) => /grade/.test(m)],
];

export class PropertyControls {
  readonly root = el("div", { class: "controls" });
  private readonly metric = el("select");
  private readonly geography = el("select");

  constructor(private readonly emit: (change: Partial<PropertySelection>) => void) {
    this.metric.addEventListener("change", () => { this.emit({ metric: this.metric.value }); });
    this.geography.addEventListener("change", () => {
      this.emit({ geography: this.geography.value as PropertySelection["geography"] });
    });
    this.root.append(labeled("Show", this.metric, "ctl-pmetric"), labeled("Map by", this.geography, "ctl-pgeo"));
  }

  render(cat: PropertyCatalog, sel: PropertySelection): void {
    this.metric.replaceChildren(
      ...GROUPS.map(([label, test]) =>
        el("optgroup", { label }, ...cat.metrics.filter((m) => test(m.metric)).map((m) => option(m.metric, m.label, m.metric === sel.metric))),
      ),
    );
    this.geography.replaceChildren(...cat.geographies.map((g) => option(g.geography, g.label, g.geography === sel.geography)));
  }
}

export function renderPropertySidebar(
  summary: HTMLElement, notes: HTMLElement, exports: HTMLElement, stats: PropertyStats, cat: PropertyCatalog,
): void {
  summary.replaceChildren(
    el("h2", {}, stats.label),
    el("p", { class: "small" }, `${stats.description} · ${stats.geography_label}`),
    el("p", { class: "small" }, `Franklin County Auditor parcels, as of ${cat.as_of}.`),
  );
  notes.replaceChildren(el("h2", {}, "Notes"), el("ul", {}, ...stats.notes.concat(cat.notes.filter((n) => !stats.notes.includes(n))).map((n) => el("li", {}, n))));
  const href = `/api/property/export.csv?${new URLSearchParams({ geography: stats.geography }).toString()}`;
  exports.replaceChildren(
    el("h2", {}, "Export this geography"),
    el("a", { href, download: true }, "CSV (every property measure)"),
    el("p", { class: "source" }, `Source: ${stats.source_file}`),
  );
}

export function renderPropertyDetail(target: HTMLElement, d: PropertyDetail, onClose: () => void): void {
  const close = el("button", { type: "button", class: "close", "aria-label": "Close details" }, "×");
  close.addEventListener("click", onClose);
  const rows = d.metrics.map((m) =>
    el("tr", {}, el("th", { scope: "row" }, m.label), el("td", { class: "num" }, m.value === null ? "—" : formatValue(m.kind, m.value)),
      el("td", { class: "num" }, m.n.toLocaleString("en-US"))),
  );
  const total = d.grades.reduce((s, g) => s + g.parcels, 0);
  target.replaceChildren(
    ...compact(
      close,
      el("h2", {}, d.name),
      el("table", { class: "choices" },
        el("thead", {}, el("tr", {}, el("th", {}, "Measure"), el("th", { class: "num" }, "Value"), el("th", { class: "num" }, "Parcels"))),
        el("tbody", {}, ...rows)),
      total ? el("p", { class: "small" }, "Construction grade: " + d.grades.map((g) => `${g.grade} ${((100 * g.parcels) / total).toFixed(0)}%`).join(" · ")) : null,
      el("p", { class: "source" }, `Source: ${d.source_file}, as of ${d.as_of}. No owner names or addresses are stored or shown.`),
    ),
  );
  target.hidden = false;
}
