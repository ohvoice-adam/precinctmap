import { describe, expect, it } from "vitest";

import { applyChange, fromParams, metricsFor, resolve, toParams } from "./state";
import { CATALOG } from "./testdata";

const GENERAL = CATALOG.elections[0]!;
const PRIMARY = CATALOG.elections[1]!;

describe("resolve", () => {
  it("defaults to the latest year, its election, and the widest contest", () => {
    const sel = resolve(CATALOG, {});
    expect(sel).toEqual({
      year: 2025, election: GENERAL.election_id, contest: "e:np:levy",
      metric: "yes_share", choice: null, geography: "precinct",
    });
  });

  it("repairs invalid fields instead of failing", () => {
    const sel = resolve(CATALOG, { e: GENERAL.election_id, c: "nope", m: "bogus", g: "zcta" });
    expect(sel?.contest).toBe("e:np:levy");
    expect(sel?.metric).toBe("yes_share");
    expect(sel?.geography).toBe("precinct"); // zcta has no data for this election
  });

  it("picks a candidate for the share metric and keeps a valid one", () => {
    expect(resolve(CATALOG, { e: GENERAL.election_id, c: "e:np:council" })?.choice).toBe("a");
    expect(resolve(CATALOG, { e: GENERAL.election_id, c: "e:np:council", ch: "b" })?.choice).toBe("b");
    expect(resolve(CATALOG, { e: GENERAL.election_id, c: "e:np:council", m: "margin", ch: "b" })?.choice).toBeNull();
  });

  it("round-trips through the URL", () => {
    const sel = resolve(CATALOG, { e: GENERAL.election_id, c: "e:np:council", ch: "b", g: "council_district" })!;
    const back = resolve(CATALOG, fromParams(`?${toParams(sel).toString()}`));
    expect(back).toEqual(sel);
    expect(toParams(sel).get("c")).toBe("e:np:council");
  });
});

describe("metricsFor", () => {
  it("offers issue metrics, candidate metrics, and turnout only when the file has it", () => {
    expect(metricsFor(GENERAL.contests[0]!, GENERAL)).toEqual(["yes_share", "margin", "total", "turnout"]);
    expect(metricsFor(GENERAL.contests[1]!, GENERAL)).toEqual(["share", "margin", "leader", "total", "turnout"]);
    expect(metricsFor(PRIMARY.contests[0]!, PRIMARY)).toEqual(["share", "total"]); // unopposed, no turnout
  });

  it("drops margin and leader for an unopposed race", () => {
    expect(metricsFor(GENERAL.contests[2]!, GENERAL)).not.toContain("margin");
  });
});

describe("applyChange", () => {
  const sel = resolve(CATALOG, { e: GENERAL.election_id, c: "e:np:council", m: "leader", g: "council_district" })!;

  it("changing the year drops election and contest but keeps preferences", () => {
    const next = resolve(CATALOG, applyChange(sel, { year: 2024 }))!;
    expect(next.election).toBe(PRIMARY.election_id);
    expect(next.metric).toBe("share"); // leader not available there
    expect(next.geography).toBe("precinct");
  });

  it("changing the geography keeps the contest and metric", () => {
    const next = resolve(CATALOG, applyChange(sel, { geography: "precinct" }))!;
    expect([next.contest, next.metric, next.geography]).toEqual(["e:np:council", "leader", "precinct"]);
  });
});
