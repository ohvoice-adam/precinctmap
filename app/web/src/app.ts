// Glue: selection -> data -> map paint, legend, notes; hover tooltip; click detail; URL state.

import { exportUrl, fetchCatalog, fetchDetail, fetchGeo, fetchPropertyDetail, fetchResults } from "./api";
import type { AreaState } from "./map/view";
import { AreaMap } from "./map/view";
import { loadProperty } from "./property/layer";
import type { PropertySelection, PropertyStats } from "./property/model";
import { propertyTooltip, resolveProperty } from "./property/model";
import { PropertyControls, renderPropertyDetail, renderPropertySidebar } from "./property/ui";
import type { AreaValue, MetricContext } from "./metrics";
import { areaValue, metricContext } from "./metrics";
import { binOf, scaleFor } from "./scales";
import type { RawSelection, Selection } from "./state";
import { applyChange, findContest, findElection, fromParams, resolve, toParams } from "./state";
import type { Catalog, Results } from "./types";
import type { Change } from "./state";
import { Controls } from "./ui/controls";
import { compact, el, labeled, option } from "./ui/dom";
import { STATUS_TEXT, marginSides, tooltipLines } from "./ui/format";
import { renderLegend } from "./ui/legend";
import { renderDetail, renderDetailError } from "./ui/panel";
import { Tooltip } from "./ui/tooltip";

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
  private readonly propertyControls = new PropertyControls((c) => void this.changeProperty(c));
  private readonly dataset = el("select");
  private readonly datasetField = labeled("Data", this.dataset, "ctl-dataset");
  private mode: "results" | "property" = "results";
  private psel: PropertySelection | null = null;
  private pstats: PropertyStats | null = null;
  private readonly summary = el("section", { class: "summary", "aria-live": "polite" });
  private readonly legend = el("section", { class: "legend" });
  private readonly notes = el("section", { class: "notes" });
  private readonly exports = el("section", { class: "exports" });
  private readonly panel = el("aside", { class: "detail", "aria-label": "Area details" });
  private readonly map: AreaMap;
  private readonly tooltip: Tooltip;

  constructor(sidebar: HTMLElement, mapEl: HTMLElement) {
    sidebar.append(this.datasetField, this.controls.root, this.propertyControls.root, this.summary, this.legend, this.notes, this.exports);
    this.dataset.addEventListener("change", () => {
      const g = (this.mode === "property" ? this.psel?.geography : this.sel?.geography) ?? "precinct";
      void this.load(this.dataset.value === "property" ? { d: "property", g } : { g }, true);
    });
    this.panel.hidden = true;
    mapEl.parentElement?.append(this.panel);
    this.map = new AreaMap(mapEl);
    this.tooltip = new Tooltip(mapEl.parentElement ?? mapEl);
    this.map.map.on("mousemove", (e) => { this.hover(e.point.x, e.point.y, this.map.hitAt(e)); });
    this.map.map.on("mouseout", () => { this.tooltip.hide(); this.map.setHover(null); });
    this.map.map.on("click", (e) => {
      const hit = this.map.hitAt(e);
      if (hit?.kind === "area") void this.openDetail(hit.featureId);
    });
    window.addEventListener("popstate", () => void this.load(fromParams(location.search), false));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") this.closeDetail(); });
  }

  async start(): Promise<void> {
    this.catalog = await fetchCatalog();
    const prop = this.catalog.property;
    this.datasetField.hidden = !prop;
    this.dataset.replaceChildren(option("results", "Election results", true),
      ...(prop ? [option("property", `Residential property (auditor, ${prop.as_of})`, false)] : []));
    if (this.catalog.elections.length === 0 && !prop) {
      this.summary.replaceChildren(el("p", {}, "No elections have been loaded yet. An admin can add one from the upload page."));
      return;
    }
    await this.map.ready;
    await this.load(fromParams(location.search), false);
  }

  private async change(c: Change): Promise<void> {
    if (this.sel) await this.load(applyChange(this.sel, c), true);
  }

  private async changeProperty(c: Partial<PropertySelection>): Promise<void> {
    if (this.psel) await this.load({ d: "property", pm: c.metric ?? this.psel.metric, g: c.geography ?? this.psel.geography }, true);
  }

  private async load(raw: RawSelection, push: boolean): Promise<void> {
    if (!this.catalog) return;
    const prop = this.catalog.property;
    const property = raw.d === "property" && prop !== null;
    this.mode = property || this.catalog.elections.length === 0 ? "property" : "results";
    this.dataset.value = this.mode;
    this.controls.root.hidden = this.mode !== "results";
    this.propertyControls.root.hidden = this.mode !== "property";
    if (this.mode === "property" && prop) {
      const psel = resolveProperty(prop, raw.pm, raw.g);
      this.psel = psel;
      const url = `?${new URLSearchParams({ d: "property", pm: psel.metric, g: psel.geography }).toString()}`;
      if (push) history.pushState(null, "", url);
      else history.replaceState(null, "", url);
      this.propertyControls.render(prop, psel);
      await this.drawProperty(psel);
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
    this.map.paint(scale.bins.map((b) => b.color), states);
    renderLegend(this.legend, scale, sel.geography, new Set([...states.values()].map((s) => s.bin)));
    this.renderSidebar(sel, results);
  }

  private async drawProperty(psel: PropertySelection): Promise<void> {
    const prop = this.catalog?.property;
    if (!prop) return;
    const token = ++this.seq;
    const d = await loadProperty(psel, prop.as_of);
    if (token !== this.seq) return;
    const key = `${d.areas.boundary_set_id}|${psel.geography}|property`;
    if (key !== this.areasKey) {
      await this.map.setAreas(d.areas, d.context, d.county);
      if (token !== this.seq) return;
      this.areasKey = key;
      this.closeDetail();
    }
    this.pstats = d.stats;
    this.map.paint(d.scale.bins.map((b) => b.color), d.states);
    renderLegend(this.legend, d.scale, psel.geography, new Set([...d.states.values()].map((s) => s.bin)), "property");
    renderPropertySidebar(this.summary, this.notes, this.exports, d.stats, prop);
  }

  private renderSidebar(sel: Selection, results: Results): void {
    if (!this.catalog) return;
    const election = findElection(this.catalog, sel);
    const contest = findContest(this.catalog, sel);
    this.summary.replaceChildren(
      ...compact(
      el("h2", {}, contest.name),
      el("p", { class: "small" }, `${election.label}${contest.party ? ` · ${contest.party} ballot` : ""} · ${results.geography_label}`),
      contest.vote_for && contest.vote_for > 1 ? el("p", { class: "small" }, `Vote for ${contest.vote_for}: shares are of all votes cast, not of voters.`) : null,
      ),
    );
    this.notes.replaceChildren(...(results.notes.length ? [el("h2", {}, "Notes"), el("ul", {}, ...results.notes.map((n) => el("li", {}, n)))] : []));
    const link = (kind: "csv" | "geojson", label: string): HTMLAnchorElement =>
      el("a", { href: exportUrl(kind, sel.election, sel.contest, sel.geography), download: true }, label);
    this.exports.replaceChildren(
      el("h2", {}, "Export this view"), link("csv", "CSV"), " · ", link("geojson", "GeoJSON"),
      el("p", { class: "source" }, `Source: ${results.source_file}`),
    );
  }

  private hover(x: number, y: number, hit: ReturnType<AreaMap["hitAt"]>): void {
    if (hit?.kind === "area" && this.mode === "property" && this.pstats) {
      this.map.setHover(hit.featureId);
      this.tooltip.show(propertyTooltip(hit.name, this.pstats, hit.featureId), x, y);
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
    this.tooltip.show(tooltipLines(hit.name, ctx.metric, v, results, marginSides(results, ctx.topTwo), method), x, y);
  }

  private async openDetail(featureId: string): Promise<void> {
    this.map.select(featureId);
    if (this.mode === "property" && this.psel) {
      try {
        renderPropertyDetail(this.panel, await fetchPropertyDetail(this.psel.geography, featureId), () => { this.closeDetail(); });
      } catch (err) {
        console.error("property detail failed", err);
        renderDetailError(this.panel, "No residential parcels in this area.");
      }
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
  }

  private closeDetail(): void {
    this.panel.hidden = true;
    this.map.select(null);
  }
}
