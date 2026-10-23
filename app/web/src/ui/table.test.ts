import { describe, expect, it, vi } from "vitest";

import type { AreaValue } from "../metrics";
import { areaValue, metricContext } from "../metrics";
import type { MeasureStats } from "../measures/model";
import type { Metric, Selection } from "../state";
import { councilResults } from "../testdata";
import type { AreaCollection } from "../types";
import type { TableRow } from "./table";
import { AreaTable, sortRows } from "./table";
import { measureTable, resultsTable } from "./table-rows";
import { effectiveView } from "./viewmode";

const row = (id: string, name: string, value: number | null, count: number | null = null): TableRow =>
  ({ id, name, value, display: "", count, countDisplay: "", note: "" });

function areas(ids: string[]): AreaCollection {
  return {
    type: "FeatureCollection", geography: "precinct", label: "Precinct", boundary_set_id: "p", retroactive: false, notes: [],
    features: ids.map((id) => ({ type: "Feature", geometry: { type: "Point", coordinates: [0, 0] }, properties: { feature_id: id, name: `COLUMBUS ${id}`, jurisdiction: null } })),
  };
}

function view(metric: Metric, choice: string | null = null) {
  const results = councilResults();
  const sel: Selection = { year: 2025, election: "e", contest: "e:np:council", metric, choice, geography: "precinct" };
  const ctx = metricContext(results, sel);
  const values = new Map<string, AreaValue>(Object.entries(results.features).map(([id, f]) => [id, areaValue(ctx, f)]));
  return resultsTable(areas(["P1", "P2", "P3", "P4", "P5"]), values, ctx, results, "Council");
}

describe("sortRows", () => {
  const rows = [row("a", "Ward 10", 0.2, 5), row("b", "Ward 2", null, 9), row("c", "Ward 1", 0.5, 1), row("d", "Ward 3", 0.2, null)];

  it("sorts values descending with areas lacking a value last", () => {
    expect(sortRows(rows, { key: "value", desc: true }).map((r) => r.id)).toEqual(["c", "d", "a", "b"]); // Ward 3 before Ward 10 on the tie
  });

  it("keeps areas lacking a value last when ascending too, breaking ties by name", () => {
    expect(sortRows(rows, { key: "value", desc: false }).map((r) => r.id)).toEqual(["d", "a", "c", "b"]);
  });

  it("sorts names in natural order (Ward 2 before Ward 10)", () => {
    expect(sortRows(rows, { key: "name", desc: false }).map((r) => r.name)).toEqual(["Ward 1", "Ward 2", "Ward 3", "Ward 10"]);
  });

  it("sorts by count", () => {
    expect(sortRows(rows, { key: "count", desc: true }).map((r) => r.id)).toEqual(["b", "a", "c", "d"]);
  });
});

describe("effectiveView", () => {
  it("defaults to side by side when wide and the map when narrow", () => {
    expect(effectiveView(null, true)).toBe("both");
    expect(effectiveView(null, false)).toBe("map");
  });

  it("falls back from side by side to the map on a narrow screen", () => {
    expect(effectiveView("both", false)).toBe("map");
    expect(effectiveView("table", false)).toBe("table");
  });
});

describe("resultsTable", () => {
  it("shows the selected candidate's share, valid votes and why areas have no value", () => {
    const spec = view("share", "a");
    expect(spec.valueLabel).toBe("Ann Lee share");
    expect(spec.caption).toBe("Council · Precinct");
    const byId = Object.fromEntries(spec.rows.map((r) => [r.id, r]));
    expect(byId.P1).toMatchObject({ display: "60.0%", count: 100, countDisplay: "100" });
    expect(byId.P1?.value).toBeCloseTo(0.6);
    expect(byId.P3?.note).toBe("Fewer than 25 votes; Includes estimates from split precincts");
    expect(byId.P4).toMatchObject({ value: null, display: "—", count: null, note: "Contest not on the ballot here" });
    expect(byId.P5?.note).toBe("No ballots cast here");
  });

  it("names the side ahead for margins", () => {
    const byId = Object.fromEntries(view("margin").rows.map((r) => [r.id, r]));
    expect(byId.P1?.display).toBe("Ann Lee +30.0");
    expect(byId.P2?.display).toBe("Bob Roe +60.0");
  });
});

describe("measureTable", () => {
  const stats = {
    dataset: "property", metric: "likely_rental_share", label: "Likely rental share", kind: "share", description: "", geography: "precinct",
    geography_label: "Precinct", boundary_set_id: "p", as_of: "2026-10-21", source_file: "Parcel.csv", notes: [],
    features: { P1: { value: 0.42, n: 120 }, P2: { value: 0.1, n: 10 }, P3: { value: null, n: 0 } },
  } satisfies MeasureStats;

  it("formats values and flags small or empty areas", () => {
    const spec = measureTable(areas(["P1", "P2", "P3", "P4"]), stats);
    expect(spec.countLabel).toBe("Residential parcels");
    const byId = Object.fromEntries(spec.rows.map((r) => [r.id, r]));
    expect(byId.P1).toMatchObject({ value: 0.42, display: "42.0%", count: 120, note: "" });
    expect(byId.P2?.note).toBe("Fewer than 25 parcels");
    expect(byId.P3).toMatchObject({ value: null, display: "—" });
    expect(byId.P4).toMatchObject({ value: null, count: null, note: "No residential parcels with this value" });
  });

  it("shows census margins of error, the universe, and unreliable estimates", () => {
    const census = {
      ...stats, dataset: "census", metric: "renter_share", label: "Renter households", universe: "households",
      features: { P1: { value: 0.6, n: 400, moe: 0.08, reliable: true }, P2: { value: 0.2, n: 30, moe: 0.15, reliable: false } },
    } satisfies MeasureStats;
    const spec = measureTable(areas(["P1", "P2", "P3"]), census);
    expect(spec.countLabel).toBe("Households");
    const byId = Object.fromEntries(spec.rows.map((r) => [r.id, r]));
    expect(byId.P1).toMatchObject({ display: "60.0% ± 8.0 points", count: 400, note: "" });
    expect(byId.P2?.note).toBe("Large margin of error");
    expect(byId.P3).toMatchObject({ value: null, note: "No estimate" });
  });
});

describe("AreaTable", () => {
  it("re-sorts on header click, marks aria-sort, and opens an area from its name", () => {
    const open = vi.fn();
    const table = new AreaTable(open, () => undefined);
    table.render({ caption: "C", valueLabel: "Share", countLabel: "Votes", source: "f.xlsx", rows: [row("a", "B area", 0.1, 1), row("b", "A area", 0.9, 2)] });
    const names = (): string[] => [...table.root.querySelectorAll("tbody th")].map((th) => th.textContent);
    expect(names()).toEqual(["A area", "B area"]); // default: value, highest first
    expect(table.current?.source).toBe("f.xlsx");
    const valueHeader = (): Element | null | undefined => table.root.querySelectorAll("thead th")[1];
    expect(valueHeader()?.getAttribute("aria-sort")).toBe("descending");
    (valueHeader()?.querySelector("button") as HTMLButtonElement).click();
    expect(names()).toEqual(["B area", "A area"]);
    expect(valueHeader()?.getAttribute("aria-sort")).toBe("ascending");
    (table.root.querySelector("tbody .area-link") as HTMLButtonElement).click();
    expect(open).toHaveBeenCalledWith("a");
    table.select("a");
    expect(table.root.querySelector("tr.selected th")?.textContent).toBe("B area");
  });
});
