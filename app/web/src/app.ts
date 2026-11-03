// Glue: selection -> data -> map paint, legend, notes; hover tooltip; click detail; URL state.

import { exportUrl, fetchCatalog, fetchDetail, fetchGeo, fetchMeasureDetail, fetchResults } from "./api";
import type { AreaState } from "./map/view";
import { AreaMap } from "./map/view";
import { loadMeasure } from "./measures/layer";
import type { Dataset, MeasureCatalog, MeasureSelection, MeasureStats } from "./measures/model";
import { measureTooltip, resolveMeasure } from "./measures/model";
import { MeasureControls, renderMeasureDetail, renderMeasureSidebar } from "./measures/ui";
import type { AreaValue, MetricContext } from "./metrics";
import { areaValue, metricContext } from "./metrics";
import { binOf, scaleFor } from "./scales";
import type { RawSelection, Selection } from "./state";
import { applyChange, findContest, findElection, fromParams, resolve, toParams } from "./state";
import type { Catalog, Results } from "./types";
import type { Change } from "./state";
import { Controls } from "./ui/controls";
import { compact, el } from "./ui/dom";
import { STATUS_TEXT, marginSides, tooltipLines } from "./ui/format";
import { measureOnlyButton } from "./ui/export";
import { AreaTable } from "./ui/table";
import { measureTable, resultsTable } from "./ui/table-rows";
import { ViewToggle } from "./ui/viewmode";
import { renderLegend } from "./ui/legend";
import { renderDetail, renderDetailError } from "./ui/panel";
import { ChipGroup } from "./ui/steps";
import { renderResultSummary } from "./ui/summary";
import { FLOATING_SHEET_QUERY, placeDetail, revealDetail, touchTracker } from "./ui/phone";
import { Tooltip } from "./ui/tooltip";

/** Short names for the Data switch (the catalog labels carry the vintage, shown in the sheet). */
const DATASET_LABELS: Record<Dataset, string> = { property: "Property", census: "Census" };

/** The stage: a bar (view switch), and a body holding the map pane, table, panel and tooltip. */
export interface Stage {
  stage: HTMLElement;
  bar: HTMLElement;
  body: HTMLElement;
  mapEl: HTMLElement;
}

interface View {
  results: Results;
  ctx: MetricContext;
  values: Map<string, AreaValue>;
}

export class App {
  private catalog: Catalog | null = null;
  private sel: Selection | null = null;
  private view: View | null = null;
  private areasKey = "";
  private seq = 0;
  private readonly controls = new Controls((c) => void this.change(c));
  private readonly measureControls = new MeasureControls((c) => void this.changeMeasure(c));
  private readonly dataset = new ChipGroup("ctl-dataset", (d) => {
    const g = (this.mode === "results" ? this.sel?.geography : this.msel?.geography) ?? "precinct";
    void this.load(d === "results" ? { g } : { d, g }, true);
  }, true);
  private mode: "results" | Dataset = "results";
  private msel: MeasureSelection | null = null;
  private mstats: MeasureStats | null = null;
  private readonly summary = el("section", { class: "summary", "aria-live": "polite" });
  private readonly legend = el("section", { class: "legend" });
  private readonly notes = el("section", { class: "notes" });
  private readonly exports = el("section", { class: "exports" });
  private readonly panel = el("aside", { class: "detail", "aria-label": "Area details" });
  private readonly map: AreaMap;
  private readonly tooltip: Tooltip;
  private readonly table = new AreaTable((id) => void this.openDetail(id), (id) => { this.map.setHover(id); });

  constructor(sidebar: HTMLElement, { stage, bar, body, mapEl }: Stage) {
    this.dataset.root.removeAttribute("aria-labelledby");
    this.dataset.root.setAttribute("aria-label", "Data");
    sidebar.append(this.dataset.root, this.controls.root, this.measureControls.root, this.summary, this.legend, this.notes, this.exports);
    this.controls.root.hidden = true; // until the catalog says which set applies
    this.measureControls.root.hidden = true;
    this.panel.hidden = true;
    body.append(this.table.root);
    placeDetail(this.panel, body, sidebar.firstElementChild ?? this.dataset.root);
    this.map = new AreaMap(mapEl);
    this.tooltip = new Tooltip(body);
    const toggle = new ViewToggle((view) => {
      stage.dataset.view = view;
      if (view !== "table") this.map.map.resize();
    });
    bar.append(toggle.root);
    toggle.apply();
    // The sheet floats over the map's left edge above phone width: keep the county out from under it.
    const floating = window.matchMedia(FLOATING_SHEET_QUERY);
    const inset = (): void => {
      this.map.setLeftInset(floating.matches ? sidebar.getBoundingClientRect().right - mapEl.getBoundingClientRect().left : 0);
    };
    floating.addEventListener("change", inset);
    void this.map.ready.then(inset);
    const touching = touchTracker(mapEl);
    this.map.map.on("mousemove", (e) => {
      if (touching()) return; // a tap: the detail panel answers it, not the hover card
      this.hover(e.point.x, e.point.y, this.map.hitAt(e));
    });
    this.map.map.on("mouseout", () => { this.tooltip.hide(); this.map.setHover(null); });
    this.map.map.on("click", (e) => {
      const hit = this.map.hitAt(e);
      if (hit?.kind === "area") void this.openDetail(hit.featureId, true);
    });
    window.addEventListener("popstate", () => void this.load(fromParams(location.search), false));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") this.closeDetail(); });
  }

  async start(): Promise<void> {
    this.catalog = await fetchCatalog();
    const measures = this.measureCatalogs();
    this.dataset.root.hidden = measures.length === 0;
    if (this.catalog.elections.length === 0 && measures.length === 0) {
      this.summary.replaceChildren(el("p", {}, "No elections have been loaded yet. An admin can add one from the upload page."));
      return;
    }
    await this.map.ready;
    await this.load(fromParams(location.search), false);
  }

  private async change(c: Change): Promise<void> {
    if (this.sel) await this.load(applyChange(this.sel, c), true);
  }

  private async changeMeasure(c: Partial<MeasureSelection>): Promise<void> {
    if (this.msel && this.mode !== "results") {
      await this.load({ d: this.mode, pm: c.metric ?? this.msel.metric, g: c.geography ?? this.msel.geography }, true);
    }
  }

  /** Loaded area-statistics datasets, in Data-selector order. */
  private measureCatalogs(): MeasureCatalog[] {
    return [this.catalog?.property, this.catalog?.census].filter((c): c is MeasureCatalog => !!c);
  }

  private async load(raw: RawSelection, push: boolean): Promise<void> {
    if (!this.catalog) return;
    const measures = this.measureCatalogs();
    const cat = measures.find((c) => c.dataset === raw.d) ?? (this.catalog.elections.length === 0 ? measures[0] : undefined);
    this.mode = cat ? cat.dataset : "results";
    this.dataset.render([{ value: "results", label: "Election results" },
      ...measures.map((c) => ({ value: c.dataset, label: DATASET_LABELS[c.dataset] }))], this.mode);
    this.controls.root.hidden = this.mode !== "results";
    this.measureControls.root.hidden = this.mode === "results";
    if (cat) {
      const msel = resolveMeasure(cat, raw.pm, raw.g);
      this.msel = msel;
      const url = `?${new URLSearchParams({ d: cat.dataset, pm: msel.metric, g: msel.geography }).toString()}`;
      if (push) history.pushState(null, "", url);
      else history.replaceState(null, "", url);
      this.measureControls.render(cat, msel);
      await this.drawMeasure(cat, msel);
      return;
    }
    const sel = resolve(this.catalog, raw);
    if (!sel) return;
    this.sel = sel;
    const url = `?${toParams(sel).toString()}`;
    if (push) history.pushState(null, "", url);
    else history.replaceState(null, "", url);
    this.controls.render(this.catalog, sel);
    await this.draw(sel);
  }

  private async draw(sel: Selection): Promise<void> {
    if (!this.catalog) return;
    const token = ++this.seq;
    const election = findElection(this.catalog, sel);
    const council = sel.geography === "council_district";
    const [areas, county, context, results] = await Promise.all([
      fetchGeo(sel.geography, election.date),
      fetchGeo("county", election.date),
      council ? fetchGeo("precinct", election.date) : Promise.resolve(null),
      fetchResults(sel.election, sel.contest, sel.geography),
    ]);
    if (token !== this.seq) return; // a newer selection superseded this one
    const key = `${areas.boundary_set_id}|${sel.geography}|results`;
    if (key !== this.areasKey) {
      await this.map.setAreas(areas, context, county);
      if (token !== this.seq) return;
      this.areasKey = key;
      this.closeDetail();
    }
    const ctx = metricContext(results, sel);
    const scale = scaleFor(ctx, results);
    const values = new Map<string, AreaValue>();
    const states = new Map<string, AreaState>();
    for (const f of areas.features) {
      const id = f.properties.feature_id;
      const v = areaValue(ctx, results.features[id]);
      values.set(id, v);
      states.set(id, { status: v.status, bin: binOf(scale, v.value, v.leader) });
    }
    this.view = { results, ctx, values };
    this.table.render(resultsTable(areas, values, ctx, results, findContest(this.catalog, sel).name));
    this.map.paint(scale.bins.map((b) => b.color), states);
    const legendKind = results.type === "turnout" ? "turnout" : "results";
    renderLegend(this.legend, scale, sel.geography, states, legendKind);
    this.renderSidebar(sel, results, ctx);
  }

  private async drawMeasure(cat: MeasureCatalog, msel: MeasureSelection): Promise<void> {
    const token = ++this.seq;
    const d = await loadMeasure(cat.dataset, msel, cat.as_of);
    if (token !== this.seq) return;
    const key = `${d.areas.boundary_set_id}|${msel.geography}|${cat.dataset}`;
    if (key !== this.areasKey) {
      await this.map.setAreas(d.areas, d.context, d.county);
      if (token !== this.seq) return;
      this.areasKey = key;
      this.closeDetail();
    }
    this.mstats = d.stats;
    this.table.render(measureTable(d.areas, d.stats));
    this.map.paint(d.scale.bins.map((b) => b.color), d.states);
    renderLegend(this.legend, d.scale, msel.geography, d.states, cat.dataset, d.stats.universe ?? undefined);
    renderMeasureSidebar(this.summary, this.notes, this.exports, d.stats, cat, this.measureOnly());
  }

  private renderSidebar(sel: Selection, results: Results, ctx: MetricContext): void {
    renderResultSummary(this.summary, results, ctx);
    this.notes.replaceChildren(...(results.notes.length ? [el("h2", {}, "Notes"), el("ul", {}, ...results.notes.map((n) => el("li", {}, n)))] : []));
    const link = (kind: "csv" | "geojson", label: string): HTMLAnchorElement | null => {
      const href = exportUrl(kind, sel.election, sel.contest, sel.geography);
      return href ? el("a", { href, download: true }, label) : null;
    };
    const geojson = link("geojson", "GeoJSON"); // turnout exports CSV only
    this.exports.replaceChildren(
      el("h2", {}, "Export this view"),
      el("p", { class: "links" }, this.measureOnly()),
      el("p", { class: "links" }, ...compact(link("csv", "CSV (every choice)"), geojson ? " · " : null, geojson)),
      el("p", { class: "source" }, `Source: ${results.source_file}`),
    );
  }

  private measureOnly(): HTMLButtonElement {
    return measureOnlyButton(() => this.table.current);
  }

  private hover(x: number, y: number, hit: ReturnType<AreaMap["hitAt"]>): void {
    if (hit?.kind === "area" && this.mode !== "results" && this.mstats) {
      this.map.setHover(hit.featureId);
      this.tooltip.show(measureTooltip(hit.name, this.mstats, hit.featureId), x, y);
      return;
    }
    if (!hit || (!this.view && hit.kind === "area")) {
      this.tooltip.hide();
      this.map.setHover(null);
      return;
    }
    if (hit.kind !== "area") {
      this.map.setHover(null);
      const text = hit.kind === "outside_county" ? STATUS_TEXT.outside_county : STATUS_TEXT.not_in_columbus;
      this.tooltip.show(hit.kind === "outside_county" ? [text] : [hit.name, text], x, y);
      return;
    }
    this.map.setHover(hit.featureId);
    if (!this.view) return;
    const { results, ctx, values } = this.view;
    const v = values.get(hit.featureId) ?? { status: "no_data" as const, value: null, valid: 0, leader: null };
    const method = results.features[hit.featureId]?.method ?? null;
    const choice = ctx.choiceIndex === null ? "" : (results.choices[ctx.choiceIndex]?.name ?? "");
    this.tooltip.show(tooltipLines(hit.name, ctx.metric, v, results, marginSides(results, ctx.topTwo), method, choice), x, y);
  }

  private async openDetail(featureId: string, fromMap = false): Promise<void> {
    this.map.select(featureId);
    this.table.select(featureId, fromMap);
    if (this.mode !== "results" && this.msel) {
      const dataset = this.mode;
      try {
        renderMeasureDetail(this.panel, await fetchMeasureDetail(dataset, this.msel.geography, featureId), () => { this.closeDetail(); });
      } catch (err) {
        console.error(`${dataset} detail failed`, err);
        renderDetailError(this.panel, dataset === "census" ? "No census estimates for this area." : "No residential parcels in this area.");
      }
      revealDetail(this.panel);
      return;
    }
    if (!this.sel) return;
    try {
      const d = await fetchDetail(this.sel.election, this.sel.contest, this.sel.geography, featureId);
      renderDetail(this.panel, d, () => { this.closeDetail(); });
    } catch (err) {
      console.error("detail failed", err);
      renderDetailError(this.panel, "Could not load details for this area.");
    }
    revealDetail(this.panel);
  }

  private closeDetail(): void {
    this.panel.hidden = true;
    this.map.select(null);
    this.table.select(null);
  }
}
