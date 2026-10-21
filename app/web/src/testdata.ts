// Small catalog and results payloads for unit tests (shapes match the API).

import type { Catalog, Results } from "./types";

const choice = (id: string, name: string, kind: string, party: string | null = null) =>
  ({ choice_id: id, name, party, kind }) as Results["choices"][number] & { kind: never };

export const CATALOG: Catalog = {
  property: null,
  years: [2025, 2024],
  elections: [
    {
      election_id: "franklin-2025-11-04-general", date: "2025-11-04", year: 2025, type: "general",
      label: "November 4, 2025 general", certified: true, source_file: "g.xlsx", turnout_parties: ["ALL"],
      geographies: [
        { geography: "precinct", label: "Precinct", boundary_set_id: "p", retroactive: false },
        { geography: "council_district", label: "Columbus council district", boundary_set_id: "c", retroactive: false },
      ],
      contests: [
        {
          contest_id: "e:np:levy", name: "Zoo levy", party: null, type: "issue", vote_for: 1,
          jurisdiction: null, precincts: 889, other_counties: [],
          choices: [choice("e:np:levy:yes", "Yes", "yes"), choice("e:np:levy:no", "No", "no"),
            choice("e:np:levy:over", "OVER VOTES", "over"), choice("e:np:levy:under", "UNDER VOTES", "under")],
        },
        {
          contest_id: "e:np:council", name: "Council", party: null, type: "candidate", vote_for: 1,
          jurisdiction: "City of Columbus", precincts: 549, other_counties: ["Delaware County"],
          choices: [choice("a", "Ann Lee", "candidate"), choice("b", "Bob Roe", "candidate"),
            choice("w", "Write-in", "write_in"), choice("o", "OVER VOTES", "over")],
        },
        {
          contest_id: "e:np:solo", name: "Unopposed", party: null, type: "candidate", vote_for: 1,
          jurisdiction: null, precincts: 10, other_counties: [],
          choices: [choice("s", "Sam Solo", "candidate"), choice("so", "OVER VOTES", "over")],
        },
      ],
    },
    {
      election_id: "franklin-2024-03-19-primary", date: "2024-03-19", year: 2024, type: "primary",
      label: "March 19, 2024 primary", certified: true, source_file: "p.xlsx", turnout_parties: [],
      geographies: [{ geography: "precinct", label: "Precinct", boundary_set_id: "pr", retroactive: true }],
      contests: [
        {
          contest_id: "e2:dem:senate", name: "U.S. Senator", party: "Dem", type: "candidate", vote_for: null,
          jurisdiction: null, precincts: 888, other_counties: [],
          choices: [choice("x", "Sherrod Brown", "candidate", "Dem")],
        },
      ],
    },
  ],
};

export function councilResults(): Results {
  return {
    election_id: "franklin-2025-11-04-general", contest_id: "e:np:council", contest: "Council",
    type: "candidate", vote_for: 1, geography: "precinct", geography_label: "Precinct",
    boundary_set_id: "p", retroactive: false, source_file: "g.xlsx",
    choices: [
      { choice_id: "a", name: "Ann Lee", party: null, kind: "candidate", counts: true },
      { choice_id: "b", name: "Bob Roe", party: null, kind: "candidate", counts: true },
      { choice_id: "w", name: "Write-in", party: null, kind: "write_in", counts: true },
      { choice_id: "o", name: "OVER VOTES", party: null, kind: "over", counts: false },
    ],
    totals: { valid_votes: 0, mapped: 0, excluded: 0 },
    notes: [],
    features: {
      P1: { v: [60, 30, 10, 5], reg: 300, bal: 110, method: "exact", pe: 1, pa: 0 },
      P2: { v: [10, 40, 0, 0], reg: 200, bal: 50, method: "exact", pe: 1, pa: 0 },
      P3: { v: [5, 4, 1, 0], reg: 20, bal: 10, method: "allocated", pe: 0, pa: 1 },
      P4: { v: null, reg: 100, bal: 40 },
      P5: { v: null, reg: 90, bal: 0 },
    },
  };
}
