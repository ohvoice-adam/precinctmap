import { describe, expect, it } from "vitest";

import { binOf } from "../scales";
import type { PropertyCatalog, PropertyKind, PropertyStats } from "./model";
import { formatValue, gradeLabel, propertyScale, propertyTooltip, resolveProperty } from "./model";

const CAT: PropertyCatalog = {
  as_of: "2026-10-21",
  source_file: "Parcel.csv",
  geographies: [
    { geography: "precinct", label: "Precinct" },
    { geography: "council_district", label: "Columbus council district" },
  ],
  metrics: [
    { metric: "likely_rentals", label: "Likely rentals", kind: "count", description: "" },
    { metric: "likely_rental_share", label: "Likely rentals, share of homes", kind: "share", description: "" },
    { metric: "median_total_value", label: "Median total value", kind: "currency", description: "" },
  ],
  notes: [],
};

describe("property selection", () => {
  it("defaults to the rental share and keeps valid choices", () => {
    expect(resolveProperty(CAT)).toEqual({ metric: "likely_rental_share", geography: "precinct" });
    expect(resolveProperty(CAT, "median_total_value", "council_district")).toEqual({ metric: "median_total_value", geography: "council_district" });
    expect(resolveProperty(CAT, "bogus", "zcta").geography).toBe("precinct");
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
    expect(binOf(propertyScale("currency", "x"), 183_100, null)).toBe(2); // $150k-200k
    expect(binOf(propertyScale("share", "x"), 0.411, null)).toBe(4); // 40-50%
    const delta = propertyScale("currency_delta", "x");
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
    const kinds: PropertyKind[] = ["count", "share", "currency", "currency_delta", "score"];
    for (const k of kinds) {
      for (const b of propertyScale(k, "x").bins) {
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
    label: "Median total value", kind: "currency",
    features: { A: { value: 254_750, n: 24_128 }, B: { value: 90_000, n: 12 }, C: { value: null, n: 0 } },
  } as unknown as PropertyStats;

  it("shows the value, the parcel count, and a caution for small areas", () => {
    expect(propertyTooltip("District 1", stats, "A")).toEqual(["District 1", "Median total value: $254,750", "24,128 homes with a value"]);
    expect(propertyTooltip("P", stats, "B").at(-1)).toMatch(/^Fewer than 25 parcels/);
    expect(propertyTooltip("P", stats, "C")).toEqual(["P", "No residential parcels with this value"]);
  });
});
