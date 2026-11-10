import { describe, expect, it } from "vitest";

import { FIT_BINS, fitBins, fitEdges, fitPercent, niceStep } from "./fit";

describe("niceStep", () => {
  it("rounds up to 1, 2, 2.5 or 5 times a power of ten", () => {
    expect(niceStep(0.0031)).toBeCloseTo(0.005);
    expect(niceStep(0.0087)).toBeCloseTo(0.01);
    expect(niceStep(0.011)).toBeCloseTo(0.02);
    expect(niceStep(0.021)).toBeCloseTo(0.025);
    expect(niceStep(0.1)).toBeCloseTo(0.1); // exact values stay
    expect(niceStep(37)).toBe(50);
  });
});

describe("fitEdges", () => {
  it("sizes bins to the item's own range, not 0-100%", () => {
    // A minor candidate: 0.5% to 4% across precincts.
    const values = Array.from({ length: 100 }, (_, i) => 0.005 + (0.035 * i) / 99);
    const edges = fitEdges(values)!;
    expect(edges).toHaveLength(FIT_BINS + 1);
    expect(edges[0]).toBe(0);
    expect(edges[1]).toBeCloseTo(0.005); // 0.5-point bins
    expect(edges[FIT_BINS - 1]).toBeCloseTo(0.035);
    expect(edges[FIT_BINS]).toBe(Number.POSITIVE_INFINITY);
  });

  it("keeps a contender's wide range on coarse bins", () => {
    const values = Array.from({ length: 100 }, (_, i) => 0.2 + (0.5 * i) / 99);
    expect(fitEdges(values)![1]).toBeCloseTo(0.1);
  });

  it("is not stretched by a few outliers above the 98th percentile", () => {
    const values = [...Array.from({ length: 200 }, () => 0.02), 0.6, 0.7];
    expect(fitEdges(values)![1]).toBeLessThan(0.01);
  });

  it("returns null when there is nothing to fit", () => {
    expect(fitEdges([])).toBeNull();
    expect(fitEdges([0, 0, 0])).toBeNull();
  });
});

describe("fitPercent", () => {
  it("adds decimals only when the step needs them", () => {
    expect(fitPercent(0.1)(0.3)).toBe("30%");
    expect(fitPercent(0.005)(0.015)).toBe("1.5%");
    expect(fitPercent(0.0005)(0.0015)).toBe("0.15%");
  });
});

describe("fitEdges without a zero anchor", () => {
  it("starts at the nice step below the smallest value (dollars, densities, ratios)", () => {
    const values = Array.from({ length: 100 }, (_, i) => 42_000 + (110_000 * i) / 99); // $42k-$152k
    const edges = fitEdges(values, false)!;
    expect(edges[0]).toBeCloseTo(40_000);
    expect(edges[1]! - edges[0]!).toBeCloseTo(20_000);
    expect(Math.min(...values)).toBeGreaterThanOrEqual(edges[0]!);
  });

  it("handles a spread that is all the same value", () => {
    expect(fitEdges([1.5, 1.5, 1.5], false)).toBeNull();
  });
});

describe("fitBins", () => {
  const colors = Array.from({ length: FIT_BINS }, (_, i) => `#00000${i}`);

  it("labels each format with the precision its step needs", () => {
    const share = Array.from({ length: 50 }, (_, i) => 0.02 + (0.05 * i) / 49);
    expect(fitBins(share, colors, "percent")?.map((b) => b.label).slice(0, 2)).toEqual(["0%–1%", "1%–2%"]);
    const money = Array.from({ length: 50 }, (_, i) => 42_000 + (110_000 * i) / 49);
    expect(fitBins(money, colors, "money", false)?.[0]?.label).toBe("$40k–$60k");
    const ratio = Array.from({ length: 50 }, (_, i) => 0.9 + (1.5 * i) / 49);
    expect(fitBins(ratio, colors, "decimal", false)?.[0]?.label).toBe("0.8–1.0");
    expect(fitBins(share, colors, "count")?.at(-1)?.label).toMatch(/\+$/);
  });

  it("covers every value: no gaps between bins, open top, and nothing left over", () => {
    const values = [0.01, 0.015, 0.03, 0.2];
    const bins = fitBins(values, colors, "percent")!;
    for (let i = 1; i < bins.length; i++) expect(bins[i]!.from).toBe(bins[i - 1]!.to);
    expect(bins.at(-1)?.to).toBe(Number.POSITIVE_INFINITY);
    for (const v of values) expect(bins.some((b) => v >= b.from && v < b.to)).toBe(true);
  });

  it("returns null with nothing to fit", () => {
    expect(fitBins([], colors, "percent")).toBeNull();
  });
});
