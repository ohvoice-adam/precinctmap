import { describe, expect, it } from "vitest";

import { binOf } from "../scales";
import type { MeasureCatalog, MeasureKind, MeasureStats } from "./model";
import { canFitKind, formatMoe, formatValue, isLow, measureTooltip, resolveMeasure } from "./model";
import { gradeLabel, measureScale } from "./scales";

const CAT: MeasureCatalog = {
  dataset: "property",
  label: "Residential property",
  as_of: "2026-10-21",
  source_file: "Parcel.csv",
  geographies: [
    { geography: "precinct", label: "Precinct" },
    { geography: "council_district", label: "Columbus council district" },
  ],
  metrics: [
    { metric: "likely_rentals", label: "Likely rentals", kind: "count", description: "", group: "Rentals" },
    { metric: "likely_rental_share", label: "Likely rentals, share of homes", kind: "share", description: "", group: "Rentals" },
    { metric: "median_total_value", label: "Median total value", kind: "currency", description: "", group: "Valuation" },
  ],
  notes: [],
};

describe("property selection", () => {
  it("defaults to the rental share and keeps valid choices", () => {
    expect(resolveMeasure(CAT)).toEqual({ metric: "likely_rental_share", geography: "precinct", scale: "fixed" });
    expect(resolveMeasure(CAT, "median_total_value", "council_district")).toEqual({ metric: "median_total_value", geography: "council_district", scale: "fixed" });
    expect(resolveMeasure(CAT, "bogus", "zcta").geography).toBe("precinct");
  });
});

describe("fitted scale", () => {
  const shares = Array.from({ length: 60 }, (_, i) => 0.02 + (0.06 * i) / 59); // a small group: 2-8%

  it("is offered for shares, counts, dollars, densities and ratios, not grades or the median gap", () => {
    const kinds: MeasureKind[] = ["share", "count", "currency", "density", "ratio"];
    for (const k of kinds) expect(canFitKind(k)).toBe(true);
    expect(canFitKind("score")).toBe(false);
    expect(canFitKind("currency_delta")).toBe(false);
  });

  it("round-trips through the selection and is dropped for measures without a fitted form", () => {
    expect(resolveMeasure(CAT, "likely_rental_share", "precinct", "rel").scale).toBe("relative");
    expect(resolveMeasure(CAT, "likely_rental_share", "precinct").scale).toBe("fixed");
    const withScore: MeasureCatalog = { ...CAT, metrics: [...CAT.metrics, { metric: "grade", label: "Grade", kind: "score", description: "", group: "Grade" }] };
    expect(resolveMeasure(withScore, "grade", "precinct", "rel").scale).toBe("fixed");
  });

  it("spreads a small share across the bins that the fixed ladder crams into two", () => {
    const fixed = measureScale("share", "x", "census");
    const fitted = measureScale("share", "x", "census", shares);
    const used = (scale: typeof fixed): number => new Set(shares.map((v) => binOf(scale, v, null))).size;
    expect(used(fixed)).toBeLessThanOrEqual(3);
    expect(used(fitted)).toBeGreaterThanOrEqual(6);
    expect(fitted.title).toContain("scale fitted to this measure");
    expect(fitted.bins).toHaveLength(fixed.bins.length);
  });

  it("keeps the fixed scale for grades, the median gap, or when there is nothing to fit", () => {
    expect(measureScale("score", "x", "property", shares).title).toBe("x");
    expect(measureScale("currency_delta", "x", "property", shares).bins).toEqual(measureScale("currency_delta", "x").bins);
    expect(measureScale("share", "x", "property", []).bins).toEqual(measureScale("share", "x").bins);
  });
});

function hue(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as [number, number, number];
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  if (d === 0) return -1;
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}

describe("property scales", () => {
  it("bins dollars, shares, and deltas at fixed edges", () => {
    expect(binOf(measureScale("currency", "x"), 183_100, null)).toBe(2); // $150k-200k
    expect(binOf(measureScale("share", "x"), 0.411, null)).toBe(4); // 40-50%
    const delta = measureScale("currency_delta", "x");
    expect(delta.bins[binOf(delta, 3_000, null)]?.label).toBe("Within $5k");
    expect(delta.bins[binOf(delta, 85_000, null)]?.label).toBe("Mean $50k+ above median");
  });

  it("names grade steps and labels mean scores", () => {
    expect(gradeLabel(3.0)).toBe("C");
    expect(gradeLabel(3.19)).toBe("C+1");
    expect(gradeLabel(3.6)).toBe("B-2");
    expect(formatValue("score", 2.736)).toBe("2.74 (about C-1)"); // nearest step is 2.8
    expect(formatValue("score", 2.42)).toBe("2.42 (about D+2)");
  });

  it("never uses party red or blue", () => {
    const kinds: MeasureKind[] = ["count", "share", "currency", "currency_delta", "score", "density", "ratio"];
    for (const k of kinds) {
      for (const b of [...measureScale(k, "x").bins, ...measureScale(k, "x", "census").bins]) {
        const h = hue(b.color); // same bands as the election palette test
        const partyRed = h >= 0 && (h < 12 || h > 345);
        const partyBlue = h >= 205 && h <= 240;
        expect(partyRed || partyBlue, `${k} ${b.color} hue ${h.toFixed(0)}`).toBe(false);
      }
    }
  });
});

describe("property tooltip", () => {
  const stats = {
    dataset: "property", label: "Median total value", kind: "currency",
    features: { A: { value: 254_750, n: 24_128 }, B: { value: 90_000, n: 12 }, C: { value: null, n: 0 } },
  } as unknown as MeasureStats;

  it("shows the value, the parcel count, and a caution for small areas", () => {
    expect(measureTooltip("District 1", stats, "A")).toEqual(["District 1", "Median total value: $254,750", "24,128 homes with a value"]);
    expect(measureTooltip("P", stats, "B").at(-1)).toMatch(/^Fewer than 25 parcels/);
    expect(measureTooltip("P", stats, "C")).toEqual(["P", "No residential parcels with this value"]);
  });

  it("keeps a value that rests on registered voters, not parcels (the campus)", () => {
    const voters = {
      dataset: "property", label: "Registered voters per square mile", kind: "density", universe: "registered voters",
      features: { CAMPUS: { value: 41_200, n: 3_900 }, SMALL: { value: 900, n: 12 } },
    } as unknown as MeasureStats;
    expect(measureTooltip("COLUMBUS 41-F", voters, "CAMPUS")).toEqual(
      ["COLUMBUS 41-F", "Registered voters per square mile: 41,200 per sq mi", "3,900 registered voters"]);
    expect(measureTooltip("P", voters, "SMALL").at(-1)).toBe("Fewer than 25 registered voters: read with care");
  });
});

describe("census measures", () => {
  const CENSUS: MeasureCatalog = {
    dataset: "census", label: "Census demographics", as_of: "2026-10-21", source_file: "ACS",
    geographies: [{ geography: "precinct", label: "Precinct" }],
    metrics: [
      { metric: "population", label: "Population", kind: "count", description: "", group: "Population" },
      { metric: "bachelors_share", label: "Bachelor's degree or higher", kind: "share", description: "", group: "Education" },
    ],
    notes: [],
  };
  const stats = {
    dataset: "census", label: "Bachelor's degree or higher", kind: "share", universe: "adults 25 and older",
    features: { A: { value: 0.452, n: 1234, moe: 0.061, reliable: true }, B: { value: 0.03, n: 80, moe: 0.04, reliable: false } },
  } as unknown as MeasureStats;

  it("defaults to the bachelor's share", () => {
    expect(resolveMeasure(CENSUS)).toEqual({ metric: "bachelors_share", geography: "precinct", scale: "fixed" });
  });

  it("shows the margin of error and the universe, and flags unreliable estimates", () => {
    expect(measureTooltip("P1", stats, "A")).toEqual(["P1", "Bachelor's degree or higher: 45.2% ± 6.1 points", "1,234 adults 25 and older"]);
    expect(measureTooltip("P2", stats, "B").at(-1)).toBe("Large margin of error: read with care");
    expect(isLow(stats, { value: 0.5, n: 10, reliable: true })).toBe(false); // census: n alone is no flag
  });

  it("formats income, density, and top-coded income", () => {
    expect(formatValue("currency", 67_500, "census")).toBe("$67,500");
    expect(formatValue("currency", 200_000, "census")).toBe("$200,000 or more");
    expect(formatValue("currency", 200_000)).toBe("$200,000"); // a $200k home value is not top-coded
    expect(formatValue("density", 4065.6)).toBe("4,066 per sq mi");
    expect(formatMoe("currency", 8_412.3)).toBe("± $8,412");
  });

  it("uses finer low bins for census shares and income bins for census currency", () => {
    expect(binOf(measureScale("share", "x", "census"), 0.07, null)).toBe(1); // 5-10%
    expect(binOf(measureScale("share", "x"), 0.07, null)).toBe(0); // property: 0-10%
    expect(binOf(measureScale("currency", "x", "census"), 67_500, null)).toBe(3); // $65k-80k
    expect(binOf(measureScale("density", "x"), 4_065, null)).toBe(5); // 4,000-5,000
  });

  it("formats and bins registered voters per housing unit", () => {
    expect(formatValue("ratio", 1.6449)).toBe("1.64");
    const ratio = measureScale("ratio", "x");
    expect(ratio.bins.map((b) => b.label)).toEqual(
      ["0.00–0.75", "0.75–1.00", "1.00–1.25", "1.25–1.50", "1.50–1.75", "1.75–2.00", "2.00–2.50", "2.50+"]);
    expect(binOf(ratio, 1.53, null)).toBe(4); // the county: 1.50-1.75
    expect(binOf(ratio, 3.83, null)).toBe(7); // top bin is open
  });
});
