// Pure helpers for the admin page: what the review report says, and whether commit is allowed.

export interface StagedReport {
  staging_id: string;
  status: string; // "ready" | "blocked" | "noop"
  report: {
    filename: string;
    blockers: string[];
    warnings: string[];
    election: { election_id: string | null; label: string; certified: boolean };
    precincts: { rows: number; out_of_county_rows: string[] };
    contests: { count: number };
    boundary_match: { boundary_set_id: string | null; matched: number; results_precincts: number; rate: number | null; results_only: string[]; retroactive: boolean };
    county_total_check: { columns: number; passed: number };
    long_format_check: { choices: number; failures: string[] };
    replaces: { filename: string; contests: number; precinct_votes: number } | null;
  };
  report_text: string;
}

/**
 * Commit only a batch the review marked ready: never blocked, never already loaded. A batch
 * that would replace a loaded file also needs the admin to confirm the replacement.
 */
export function canCommit(staged: StagedReport | null, replaceConfirmed = false): boolean {
  if (staged?.status !== "ready" || staged.report.blockers.length > 0) return false;
  return staged.report.replaces === null || replaceConfirmed;
}

export function statusText(staged: StagedReport): string {
  switch (staged.status) {
    case "ready":
      return "Ready to add to the map";
    case "blocked":
      return "Blocked: fix the problems below, then review again";
    case "noop":
      return "Already loaded: this exact file is in the catalog";
    default:
      return staged.status;
  }
}

export function facts(staged: StagedReport): [string, string][] {
  const r = staged.report;
  const m = r.boundary_match;
  const rate = m.rate === null ? "no boundary set" : `${m.matched} of ${m.results_precincts} (${(m.rate * 100).toFixed(1)}%)`;
  return [
    ["Election", r.election.election_id ? r.election.label : "Not identified"],
    ["Certified", r.election.certified ? "Yes" : "No"],
    ["Precincts", String(r.precincts.rows)],
    ["Precinct match", `${rate}${m.retroactive ? ", boundaries applied retroactively" : ""}`],
    ["Unmatched precincts", m.results_only.length ? m.results_only.join(", ") : "None"],
    ["County-total check", `${r.county_total_check.passed} of ${r.county_total_check.columns} columns reconcile`],
    ["Contests", String(r.contests.count)],
    ...(r.replaces
      ? ([["Replaces", `${r.replaces.filename} (${r.replaces.contests} contests now loaded)`]] as [string, string][])
      : []),
  ];
}
