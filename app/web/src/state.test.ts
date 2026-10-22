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

const TURNOUT_GENERAL = GENERAL.contests.find((c) => c.type === "turnout")!;
const TURNOUT_PRIMARY = PRIMARY.contests.find((c) => c.type === "turnout")!;

describe("metricsFor", () => {
  it("offers issue and candidate metrics; turnout lives in its own entry", () => {
    expect(metricsFor(GENERAL.contests[0]!)).toEqual(["yes_share", "margin", "total"]);
    expect(metricsFor(GENERAL.contests[1]!)).toEqual(["share", "margin", "leader", "total"]);
    expect(metricsFor(PRIMARY.contests[0]!)).toEqual(["share", "total"]); // unopposed
  });

  it("drops margin and leader for an unopposed race", () => {
    expect(metricsFor(GENERAL.contests[2]!)).not.toContain("margin");
  });

  it("offers party ballot measures only when the file has party ballots", () => {
    expect(metricsFor(TURNOUT_GENERAL)).toEqual(["turnout", "ballots"]);
    expect(metricsFor(TURNOUT_PRIMARY)).toEqual(["turnout", "ballots", "party_turnout", "party_share", "party_ballots"]);
  });
});

describe("turnout selection", () => {
  it("is never the default contest, even though it covers every precinct", () => {
    expect(resolve(CATALOG, { e: PRIMARY.election_id })?.contest).toBe("e2:dem:senate");
  });

  it("picks a party ballot for party measures and round-trips through the URL", () => {
    const sel = resolve(CATALOG, { e: PRIMARY.election_id, c: TURNOUT_PRIMARY.contest_id, m: "party_share", ch: "t:Rep" })!;
    expect([sel.metric, sel.choice]).toEqual(["party_share", "t:Rep"]);
    expect(resolve(CATALOG, fromParams(`?${toParams(sel).toString()}`))).toEqual(sel);
    const overall = resolve(CATALOG, { e: PRIMARY.election_id, c: TURNOUT_PRIMARY.contest_id, m: "turnout", ch: "t:Rep" })!;
    expect(overall.choice).toBeNull();
  });

  it("falls back to overall turnout where there are no party ballots", () => {
    const sel = resolve(CATALOG, { e: GENERAL.election_id, c: TURNOUT_GENERAL.contest_id, m: "party_share" })!;
    expect([sel.metric, sel.choice]).toEqual(["turnout", null]);
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
