// Mirrors app/api/models.py (the API contract).

import type { MeasureCatalog } from "./measures/model";

export type Geography = "precinct" | "council_district" | "municipality" | "zcta";
export type ChoiceKind =
  | "candidate"
  | "yes"
  | "no"
  | "write_in"
  | "withdrawn"
  | "no_petition"
  | "over"
  | "under"
  | "party"; // a party's ballots (turnout)

export interface Choice {
  choice_id: string;
  name: string;
  party: string | null;
  kind: ChoiceKind;
}

export interface CatalogContest {
  contest_id: string;
  name: string;
  party: string | null;
  type: "candidate" | "issue" | "turnout";
  vote_for: number | null;
  jurisdiction: string | null;
  precincts: number;
  other_counties: string[];
  choices: Choice[];
}

export interface CatalogGeography {
  geography: Geography;
  label: string;
  boundary_set_id: string;
  retroactive: boolean;
}

export interface CatalogElection {
  election_id: string;
  date: string;
  year: number;
  type: string;
  label: string;
  certified: boolean;
  source_file: string | null;
  turnout_parties: string[];
  geographies: CatalogGeography[];
  contests: CatalogContest[];
}

export interface Catalog {
  years: number[];
  elections: CatalogElection[];
  property: MeasureCatalog | null;
  census?: MeasureCatalog | null;
}

export interface ResultChoice extends Choice {
  counts: boolean;
}

export interface FeatureResult {
  v: number[] | null;
  reg: number | null;
  bal: number | null;
  method?: "exact" | "allocated" | "mixed" | null;
  pe?: number | null;
  pa?: number | null;
}

export interface Results {
  election_id: string;
  contest_id: string;
  contest: string;
  type: "candidate" | "issue" | "turnout";
  vote_for: number | null;
  geography: Geography;
  geography_label: string;
  boundary_set_id: string;
  retroactive: boolean;
  source_file: string;
  choices: ResultChoice[];
  totals: { valid_votes: number | null; mapped: number | null; excluded: number | null };
  notes: string[];
  features: Record<string, FeatureResult>;
}

export interface DetailChoice extends ResultChoice {
  votes: number;
  share: number | null;
}

export interface Detail {
  feature_id: string;
  name: string;
  on_ballot: boolean;
  valid_votes: number;
  retroactive: boolean;
  choices: DetailChoice[];
  method: string | null;
  contributions: {
    precinct: string;
    split_share: number;
    method: string;
    weight_basis: string;
    precinct_valid_votes: number | null;
  }[];
  turnout: { registered: number | null; ballots_cast: number | null; turnout: number | null } | null;
  source_file: string;
  source_sha256: string;
}

export interface AreaProperties {
  feature_id: string;
  name: string;
  jurisdiction: string | null;
}

export interface AreaCollection extends GeoJSON.FeatureCollection<GeoJSON.Geometry, AreaProperties> {
  geography: string;
  label: string;
  boundary_set_id: string;
  retroactive: boolean;
  notes: string[];
}

/** /api/turnout/detail: one area's registered voters, ballots and party ballots. */
export interface TurnoutDetail {
  feature_id: string;
  name: string;
  jurisdiction: string | null;
  geography: string;
  boundary_set_id: string;
  retroactive: boolean;
  registered: number | null;
  ballots_cast: number | null;
  turnout: number | null;
  parties: { party: string; label: string; ballots: number | null; of_registered: number | null; of_ballots: number | null }[];
  method: string | null;
  contributions: { precinct: string; split_share: number; method: string; weight_basis: string; precinct_ballots: number | null }[];
  source_file: string;
  source_sha256: string;
}
