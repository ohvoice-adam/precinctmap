import { describe, expect, it } from "vitest";

import { LOW_VOTE_THRESHOLD, areaValue, metricContext } from "./metrics";
import { binOf, LEADER_COLORS, OTHER_COLOR, SEQUENTIAL, scaleFor } from "./scales";
import type { Metric, Selection } from "./state";
import { councilResults } from "./testdata";
import { STATUS_TEXT, tooltipLines } from "./ui/format";

function ctxFor(metric: Metric, choice: string | null = null) {
  const sel: Selection = { year: 2025, election: "e", contest: "e:np:council", metric, choice, geography: "precinct" };
  return metricContext(councilResults(), sel);
}

describe("areaValue", () => {
  const r = councilResults();

  it("uses valid votes (over-votes excluded) for shares", () => {
    const a = areaValue(ctxFor("share", "a"), r.features.P1);
    expect(a).toMatchObject({ status: "value", valid: 100 });
    expect(a.value).toBeCloseTo(0.6);
  });

  it("measures margins between the contest-wide top two", () => {
    const ctx = ctxFor("margin");
    expect(ctx.topTwo).toEqual([0, 1]); // Ann 75 vs Bob 74 overall
    expect(areaValue(ctx, r.features.P2).value).toBeCloseTo(-0.6); // Bob ahead there
  });

  it("names the area's leader", () => {
    expect(areaValue(ctxFor("leader"), r.features.P2).leader).toBe("1");
  });

  it("separates not on ballot, no ballots cast, no data, and low counts", () => {
    const ctx = ctxFor("share", "a");
    expect(areaValue(ctx, r.features.P4).status).toBe("not_on_ballot");
    expect(areaValue(ctx, r.features.P5).status).toBe("no_ballots");
    expect(areaValue(ctx, undefined).status).toBe("no_data");
    const low = areaValue(ctx, r.features.P3);
    expect(low.status).toBe("low");
    expect(low.valid).toBeLessThan(LOW_VOTE_THRESHOLD);
  });

  it("turnout comes from ballots / registered even where the contest was absent", () => {
    expect(areaValue(ctxFor("turnout"), r.features.P4).value).toBeCloseTo(0.4);
  });
});

describe("scales", () => {
  it("bins shares into fixed ranges", () => {
    const scale = scaleFor(ctxFor("share", "a"), councilResults());
    expect(scale.bins).toHaveLength(SEQUENTIAL.length);
    expect(binOf(scale, 0.6, null)).toBe(5); // 60-70%
    expect(binOf(scale, 1, null)).toBe(7);
    expect(binOf(scale, null, null)).toBe(-1);
  });

  it("labels the margin arms with candidate names and a neutral middle", () => {
    const scale = scaleFor(ctxFor("margin"), councilResults());
    expect(scale.bins[3]?.label).toBe("Within 5 points");
    expect(scale.bins[6]?.label).toBe("Ann Lee by 30+");
    expect(scale.bins[0]?.label).toBe("Bob Roe by 30+");
  });

  it("colors leaders by contest-wide rank and folds the rest into Other", () => {
    const scale = scaleFor(ctxFor("leader"), councilResults());
    expect(scale.bins.map((b) => b.color)).toEqual([...LEADER_COLORS]);
    expect(binOf(scale, 0.5, "1")).toBe(1);
    const many = { ...ctxFor("leader"), rank: [0, 1, 2, 3] };
    expect(scaleFor(many, councilResults()).bins.at(-1)?.color).toBe(OTHER_COLOR);
  });

  it("never uses party red or blue for data", () => {
    const hue = (hex: string): number => {
      const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as [number, number, number];
      const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
      if (d === 0) return -1;
      const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
      return (h * 60 + 360) % 360;
    };
    const metrics: Metric[] = ["share", "margin", "leader", "total", "turnout", "yes_share"];
    for (const m of metrics) {
      for (const bin of scaleFor(ctxFor(m, "a"), councilResults()).bins) {
        const h = hue(bin.color);
        const partyRed = h >= 0 && (h < 12 || h > 345);
        const partyBlue = h >= 205 && h <= 240;
        expect(partyRed || partyBlue, `${m} ${bin.color} hue ${h.toFixed(0)}`).toBe(false);
      }
    }
  });
});

describe("tooltip text", () => {
  const r = councilResults();
  it("explains a missing value instead of showing zero", () => {
    const lines = tooltipLines("P4", "share", areaValue(ctxFor("share", "a"), r.features.P4), r, ["Ann Lee", "Bob Roe"]);
    expect(lines).toEqual(["P4", STATUS_TEXT.not_on_ballot]);
  });

  it("shows the count, the low-vote caution, and estimation for split precincts", () => {
    const lines = tooltipLines("P3", "margin", areaValue(ctxFor("margin"), r.features.P3), r, ["Ann Lee", "Bob Roe"], "allocated");
    expect(lines).toContain("Ann Lee ahead by 10.0 points");
    expect(lines).toContain("10 valid votes");
    expect(lines.some((l) => l.startsWith("Fewer than 25 votes"))).toBe(true);
    expect(lines).toContain("Includes estimates from split precincts");
  });
});

describe("turnout measures", () => {
  const results = {
    ...councilResults(),
    type: "turnout" as const,
    choices: [
      { choice_id: "t:Dem", name: "Democratic ballots", party: "Dem", kind: "party" as const, counts: true },
      { choice_id: "t:Rep", name: "Republican ballots", party: "Rep", kind: "party" as const, counts: true },
    ],
    features: { A: { v: [60, 30], reg: 300, bal: 100 }, B: { v: [2, 1], reg: 20, bal: 4 }, C: { v: [0, 0], reg: 50, bal: 0 } },
  };
  const ctx = (metric: Metric, choice: string | null = null) =>
    metricContext(results, { year: 2024, election: "e", contest: "e:turnout", metric, choice, geography: "precinct" });

  it("divides by registered voters or by ballots cast, and counts ballots", () => {
    expect(areaValue(ctx("turnout"), results.features.A).value).toBeCloseTo(100 / 300);
    expect(areaValue(ctx("ballots"), results.features.A)).toMatchObject({ value: 100, valid: 100 });
    expect(areaValue(ctx("party_turnout", "t:Dem"), results.features.A).value).toBeCloseTo(0.2);
    expect(areaValue(ctx("party_share", "t:Dem"), results.features.A).value).toBeCloseTo(0.6);
    expect(areaValue(ctx("party_ballots", "t:Rep"), results.features.A).value).toBe(30);
  });

  it("flags small denominators and areas with no ballots", () => {
    expect(areaValue(ctx("turnout"), results.features.B).status).toBe("low"); // 20 registered
    expect(areaValue(ctx("party_share", "t:Dem"), results.features.B).status).toBe("low"); // 4 ballots
    expect(areaValue(ctx("party_share", "t:Dem"), results.features.C).status).toBe("no_ballots");
    expect(areaValue(ctx("turnout"), results.features.C).value).toBe(0); // registered voters, nobody voted
  });

  it("names the party ballot in the tooltip", () => {
    const a = areaValue(ctx("party_turnout", "t:Dem"), results.features.A);
    expect(tooltipLines("P1", "party_turnout", a, results, ["?", "?"], "exact", "Democratic ballots"))
      .toEqual(["P1", "Democratic ballots: 20.0% of registered voters", "100 ballots cast"]);
  });
});
