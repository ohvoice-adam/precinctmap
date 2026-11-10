// Area-statistics UI: controls (measure, geography), detail panel, sidebar notes and export.

import { compact, el, option } from "../ui/dom";
import { ChipGroup, Picker, step } from "../ui/steps";
import type { MeasureCatalog, MeasureDetail, MeasureSelection, MeasureStats } from "./model";
import { canFitKind, formatMoe, formatValue } from "./model";

/** Property and census steps: measure (grouped by topic), then geography. */
export class MeasureControls {
  readonly root = el("div", { class: "controls steps" });
  private readonly metric = new Picker("ctl-pmetric", (v) => { this.emit({ metric: v }); }, true);
  private readonly geography = new ChipGroup("ctl-pgeo", (v) => {
    this.emit({ geography: v as MeasureSelection["geography"] });
  });

  private readonly scale = new ChipGroup("ctl-pscale", (v) => { this.emit({ scale: v as MeasureSelection["scale"] }); }, true);
  private readonly scaleField = el("div", { class: "subfield" },
    el("span", { class: "sub-label", id: "ctl-pscale-label" }, "Color scale"), this.scale.root);

  constructor(private readonly emit: (change: Partial<MeasureSelection>) => void) {
    this.root.append(step(1, "Measure", "ctl-pmetric", this.metric.root, this.scaleField), step(2, "Map by", "ctl-pgeo", this.geography.root));
  }

  /** Measures are listed under their group headings, in catalog order. */
  render(cat: MeasureCatalog, sel: MeasureSelection): void {
    const groups = [...new Set(cat.metrics.map((m) => m.group))];
    this.metric.select.replaceChildren(
      ...groups.map((group) =>
        el("optgroup", { label: group }, ...cat.metrics.filter((m) => m.group === group).map((m) => option(m.metric, m.label, m.metric === sel.metric))),
      ),
    );
    this.metric.sync(true);
    // Fixed bins are one ladder for every area; fitted bins follow this measure's own spread, so a
    // small group's geography shows. Not offered for grades or the mean-minus-median gap.
    const kind = cat.metrics.find((m) => m.metric === sel.metric)?.kind;
    this.scaleField.hidden = kind === undefined || !canFitKind(kind);
    this.scale.render([{ value: "fixed", label: "Fixed bins" }, { value: "relative", label: "Fit to this measure" }], sel.scale);
    this.geography.render(cat.geographies.map((g) => ({ value: g.geography, label: g.label })), sel.geography);
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
  // The measure's name is already the step 1 picker; the summary says what it counts.
  summary.replaceChildren(
    el("p", { class: "scope" }, stats.universe ? `${stats.geography_label}, ${stats.universe}` : stats.geography_label),
    el("p", { class: "small" }, stats.description),
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
      el("td", { class: "num", title: m.universe ?? undefined },
        d.dataset === "census" ? m.n.toLocaleString("en-US") : `${m.n.toLocaleString("en-US")} ${m.universe ?? "parcels"}`));
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
        el("thead", {}, el("tr", {}, el("th", {}, "Measure"), el("th", { class: "num" }, "Value"), el("th", { class: "num" }, census ? "Base" : "Based on"))),
        el("tbody", {}, ...detailRows(d))),
      total ? el("p", { class: "small" }, "Construction grade: " + d.grades.map((g) => `${g.grade} ${((100 * g.parcels) / total).toFixed(0)}%`).join(" · ")) : null,
      el("p", { class: "source" }, footer),
    ),
  );
  target.hidden = false;
}
