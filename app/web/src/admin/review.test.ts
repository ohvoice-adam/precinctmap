import { describe, expect, it } from "vitest";

import type { StagedReport } from "./review";
import { canCommit, facts, statusText } from "./review";

function staged(status: string, blockers: string[] = []): StagedReport {
  return {
    staging_id: "stg-000000000000",
    status,
    report_text: "",
    report: {
      filename: "2025-General.xlsx",
      blockers,
      warnings: [],
      election: { election_id: status === "blocked" ? null : "franklin-2025-11-04-general", label: "November 4, 2025 general", certified: true },
      precincts: { rows: 889, out_of_county_rows: [] },
      contests: { count: 128 },
      boundary_match: { boundary_set_id: "p", matched: 889, results_precincts: 889, rate: 1, results_only: [], retroactive: false },
      county_total_check: { columns: 619, passed: 619 },
      long_format_check: { choices: 616, failures: [] },
      replaces: null,
    },
  };
}

describe("admin review gating", () => {
  it("enables commit only for a ready report with no blockers", () => {
    expect(canCommit(staged("ready"))).toBe(true);
    expect(canCommit(staged("blocked", ["election date unknown"]))).toBe(false);
    expect(canCommit(staged("noop"))).toBe(false);
    expect(canCommit(staged("ready", ["late blocker"]))).toBe(false);
    expect(canCommit(null)).toBe(false);
  });

  it("requires confirmation before replacing a loaded file", () => {
    const s = staged("ready");
    s.report.replaces = { filename: "old.xlsx", contests: 128, precinct_votes: 3_000_000 };
    expect(canCommit(s)).toBe(false);
    expect(canCommit(s, true)).toBe(true);
    expect(Object.fromEntries(facts(s))["Replaces"]).toBe("old.xlsx (128 contests now loaded)");
  });

  it("explains the status and the key checks in plain words", () => {
    expect(statusText(staged("noop"))).toMatch(/Already loaded/);
    const f = Object.fromEntries(facts(staged("ready")));
    expect(f["Precinct match"]).toBe("889 of 889 (100.0%)");
    expect(f["County-total check"]).toBe("619 of 619 columns reconcile");
    expect(Object.fromEntries(facts(staged("blocked")))["Election"]).toBe("Not identified");
  });
});
