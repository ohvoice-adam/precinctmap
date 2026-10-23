// Area-statistics UI: controls (measure, geography), detail panel, sidebar notes and export.

import { compact, el, labeled, option } from "../ui/dom";
import type { MeasureCatalog, MeasureDetail, MeasureSelection, MeasureStats } from "./model";
import { formatMoe, formatValue } from "./model";

export class MeasureControls {
  readonly root = el("div", { class: "controls" });
  private readonly metric = el("select");
  private readonly geography = el("select");

  constructor(private readonly emit: (change: Partial<MeasureSelection>) => void) {
    this.metric.addEventListener("change", () => { this.emit({ metric: this.metric.value }); });
    this.geography.addEventListener("change", () => {
      this.emit({ geography: this.geography.value as MeasureSelection["geography"] });
    });
    this.root.append(labeled("Show", this.metric, "ctl-pmetric"), labeled("Map by", this.geography, "ctl-pgeo"));
  }

  /** Measures are listed under their group headings, in catalog order. */
  render(cat: MeasureCatalog, sel: MeasureSelection): void {
    const groups = [...new Set(cat.metrics.map((m) => m.group))];
    this.metric.replaceChildren(
      ...groups.map((group) =>
        el("optgroup", { label: group }, ...cat.metrics.filter((m) => m.group === group).map((m) => option(m.metric, m.label, m.metric === sel.metric))),
      ),
    );
    this.geography.replaceChildren(...cat.geographies.map((g) => option(g.geography, g.label, g.geography === sel.geography)));
  }
}

function sourceLine(stats: MeasureStats, cat: MeasureCatalog): string {
  return stats.dataset === "census"
    ? `U.S. Census Bureau, ${stats.source_file}. Boundaries as of ${cat.as_of}.`
    : `Franklin County Auditor parcels, as of ${cat.as_of}.`;
}

export function renderMeasureSidebar(
  summary: HTMLElement, notes: HTMLElement, exports: HTMLElement, stats: MeasureStats, cat: MeasureCatalog,
  measureOnly: HTMLElement,
): void {
  summary.replaceChildren(
    el("h2", {}, stats.label),
    el("p", { class: "small" }, `${stats.description} · ${stats.geography_label}`),
    el("p", { class: "small" }, sourceLine(stats, cat)),
  );
  notes.replaceChildren(el("h2", {}, "Notes"), el("ul", {}, ...stats.notes.concat(cat.notes.filter((n) => !stats.notes.includes(n))).map((n) => el("li", {}, n))));
  const href = `/api/${stats.dataset}/export.csv?${new URLSearchParams({ geography: stats.geography }).toString()}`;
  const what = stats.dataset === "census" ? "every census measure, with margins of error" : "every property measure";
  exports.replaceChildren(
    el("h2", {}, "Export this geography"),
    el("p", { class: "links" }, measureOnly),
    el("p", { class: "links" }, el("a", { href, download: true }, `CSV (${what})`)),
    el("p", { class: "source" }, `Source: ${stats.source_file}`),
  );
}

function detailRows(d: MeasureDetail): HTMLTableRowElement[] {
  return d.metrics.map((m) => {
    const moe = m.value !== null && m.moe !== null && m.moe !== undefined ? ` ${formatMoe(m.kind, m.moe)}` : "";
    const value = m.value === null ? "—" : `${formatValue(m.kind, m.value, d.dataset)}${moe}${m.reliable === false ? " †" : ""}`;
    return el("tr", {}, el("th", { scope: "row" }, m.label), el("td", { class: "num" }, value),
      el("td", { class: "num", title: m.universe ?? undefined }, m.n.toLocaleString("en-US")));
  });
}

export function renderMeasureDetail(target: HTMLElement, d: MeasureDetail, onClose: () => void): void {
  const close = el("button", { type: "button", class: "close", "aria-label": "Close details" }, "×");
  close.addEventListener("click", onClose);
  const census = d.dataset === "census";
  const total = d.grades.reduce((s, g) => s + g.parcels, 0);
  const footer = census
    ? `Source: ${d.source_file}. † Large margin of error (coefficient of variation above 30%). Margins are 90%.`
    : `Source: ${d.source_file}, as of ${d.as_of}. No owner names or addresses are stored or shown.`;
  target.replaceChildren(
    ...compact(
      close,
      el("h2", {}, d.name),
      el("table", { class: "choices" },
        el("thead", {}, el("tr", {}, el("th", {}, "Measure"), el("th", { class: "num" }, "Value"), el("th", { class: "num" }, census ? "Base" : "Parcels"))),
        el("tbody", {}, ...detailRows(d))),
      total ? el("p", { class: "small" }, "Construction grade: " + d.grades.map((g) => `${g.grade} ${((100 * g.parcels) / total).toFixed(0)}%`).join(" · ")) : null,
      el("p", { class: "source" }, footer),
    ),
  );
  target.hidden = false;
}
