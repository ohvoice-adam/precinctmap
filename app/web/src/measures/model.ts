// Area-statistics datasets (auditor property, census demographics): API types, selection,
// and plain-language text. Census values carry a 90% margin of error and a reliability flag.

import type { Geography } from "../types";
import { gradeLabel, num } from "./scales";

export type Dataset = "property" | "census";
export type MeasureKind = "count" | "share" | "currency" | "currency_delta" | "score" | "density";

export interface MeasureMetric {
  metric: string;
  label: string;
  kind: MeasureKind;
  description: string;
  group: string;
  universe?: string | null;
}

export interface MeasureCatalog {
  dataset: Dataset;
  label: string;
  as_of: string;
  source_file: string;
  geographies: { geography: Geography; label: string }[];
  metrics: MeasureMetric[];
  notes: string[];
}

export interface MeasureValue {
  value: number | null;
  n: number;
  moe?: number | null;
  reliable?: boolean | null;
}

export interface MeasureStats {
  dataset: Dataset;
  metric: string;
  label: string;
  kind: MeasureKind;
  description: string;
  universe?: string | null;
  geography: Geography;
  geography_label: string;
  boundary_set_id: string;
  as_of: string;
  source_file: string;
  notes: string[];
  features: Record<string, MeasureValue>;
}

export interface MeasureDetail {
  dataset: Dataset;
  feature_id: string;
  name: string;
  as_of: string;
  source_file: string;
  metrics: { metric: string; label: string; kind: MeasureKind; universe?: string | null; value: number | null; n: number; moe?: number | null; reliable?: boolean | null }[];
  grades: { grade: string; parcels: number }[];
}

export interface MeasureSelection {
  metric: string;
  geography: Geography;
}

/** Property areas with fewer residential parcels than this are hatched. */
export const LOW_PARCEL_THRESHOLD = 25;
/** Census median income is top-coded at the highest bracket's lower edge. */
export const INCOME_TOP = 200_000;

const DEFAULT_METRIC: Record<Dataset, string> = { property: "likely_rental_share", census: "bachelors_share" };

export function resolveMeasure(cat: MeasureCatalog, metric?: string, geography?: string): MeasureSelection {
  const fallback = DEFAULT_METRIC[cat.dataset];
  const m = cat.metrics.find((x) => x.metric === metric) ?? cat.metrics.find((x) => x.metric === fallback) ?? cat.metrics[0];
  const g = cat.geographies.find((x) => x.geography === geography) ?? cat.geographies[0];
  return { metric: m?.metric ?? fallback, geography: g?.geography ?? "precinct" };
}

export function formatValue(kind: MeasureKind, value: number, dataset: Dataset = "property"): string {
  switch (kind) {
    case "share":
      return `${(value * 100).toFixed(1)}%`;
    case "currency":
      if (dataset === "census" && value >= INCOME_TOP) return "$200,000 or more"; // top bracket
      return `$${Math.round(value).toLocaleString("en-US")}`;
    case "currency_delta":
      return `${value >= 0 ? "+" : "−"}$${Math.abs(Math.round(value)).toLocaleString("en-US")} (mean ${value >= 0 ? "above" : "below"} median)`;
    case "score":
      return `${value.toFixed(2)} (about ${gradeLabel(value)})`;
    case "density":
      return `${num(value)} per sq mi`;
    default:
      return num(value);
  }
}

/** The margin of error in the value's units: "± 6.1 points", "± $8,400", "± 120". */
export function formatMoe(kind: MeasureKind, moe: number): string {
  if (kind === "share") return `± ${(moe * 100).toFixed(1)} points`;
  if (kind === "currency") return `± $${Math.round(moe).toLocaleString("en-US")}`;
  return `± ${num(moe)}`;
}

/** What `n` counts, for tooltips and the table's count column. */
export function baseLabel(stats: Pick<MeasureStats, "dataset" | "kind" | "universe">): string {
  if (stats.dataset === "census") return stats.universe ?? "people";
  if (stats.kind === "currency" || stats.kind === "currency_delta") return "homes with a value";
  return stats.kind === "score" ? "graded homes" : "residential parcels";
}

export function isLow(stats: Pick<MeasureStats, "dataset">, v: MeasureValue): boolean {
  return stats.dataset === "census" ? v.reliable === false : v.n < LOW_PARCEL_THRESHOLD;
}

export function measureTooltip(name: string, stats: MeasureStats, featureId: string): string[] {
  const f = stats.features[featureId];
  const empty = stats.dataset === "census" ? "No estimate for this area" : "No residential parcels with this value";
  if (!f || f.n === 0 || f.value === null) return [name, empty];
  const moe = f.moe !== null && f.moe !== undefined ? ` ${formatMoe(stats.kind, f.moe)}` : "";
  const lines = [name, `${stats.label}: ${formatValue(stats.kind, f.value, stats.dataset)}${moe}`, `${num(f.n)} ${baseLabel(stats)}`];
  if (isLow(stats, f)) {
    lines.push(stats.dataset === "census" ? "Large margin of error: read with care" : `Fewer than ${LOW_PARCEL_THRESHOLD} parcels: read with care`);
  }
  return lines;
}
